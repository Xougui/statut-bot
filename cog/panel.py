import asyncio
import datetime
import json  # Importation pour la gestion des fichiers JSON
import os
import traceback  # Importation pour le débogage des traces d'erreurs

import discord
from discord.ext import commands, tasks
from dotenv import (
    load_dotenv,  # Pour charger les variables d'environnement depuis un fichier .env
)
from pydactyl.api_client import PterodactylClient

import PARAM  # Importe les variables de configuration depuis le fichier PARAM.py

# --- Configuration du Bot et de Pterodactyl ---
load_dotenv()  # Charge les variables du fichier .env
apikey1 = os.getenv("API_XOUXOU")
apikey2 = os.getenv("API_KATABUMP")

PTERODACTYL_CONFIGS = {
    "xouxou_hosting": {"url": "https://panel.xouxou-hosting.fr", "api_key": apikey1},
    "katabump_hosting": {"url": "https://control.katabump.com", "api_key": apikey2},
}

SERVERS = {
    "Lyxios": {"id": "0fc94e2a", "panel_key": "xouxou_hosting"},
    "Lyxios Manage": {"id": "063a03b1", "panel_key": "katabump_hosting"},
}

# L'ID du canal où le panel est envoyé.
CHANNEL_ID = 1373664847786545272
MESSAGE_FILE = "message_panel.json"  # Nom du fichier pour stocker l'ID du message

# --- Classes d'Interface Utilisateur (Discord UI) ---
couleur = PARAM.couleur
owners = PARAM.owners


class ServerDropdown(discord.ui.Select):
    """
    Menu déroulant pour sélectionner un serveur à contrôler.
    """

    def __init__(self, cog_instance):
        self.cog = cog_instance
        options = [discord.SelectOption(label=name, value=name) for name in SERVERS]
        super().__init__(
            placeholder="Choisissez un bot",
            options=options,
            custom_id="server_select_dropdown",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """
        Callback appelé lorsque l'utilisateur sélectionne une option dans le menu déroulant.
        """
        self.cog.selected_server = self.values[0]
        await interaction.response.defer()
        await self.cog.update_embed()


class ServerControlView(discord.ui.View):
    """
    Vue contenant les boutons de contrôle et le menu déroulant pour les serveurs.
    """

    def __init__(self, cog_instance):
        super().__init__(timeout=None)
        self.cog = cog_instance
        self.add_item(ServerDropdown(self.cog))

    @discord.ui.button(
        label="Démarrer", style=discord.ButtonStyle.green, custom_id="start_button"
    )
    async def start_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """
        Callback pour le bouton 'Démarrer'.
        """
        await interaction.response.defer(ephemeral=True)
        server_name = self.cog.selected_server
        server_id = SERVERS[server_name]["id"]
        panel_key = SERVERS[server_name]["panel_key"]
        api_client = self.cog.pterodactyl_clients.get(panel_key)

        if not api_client:
            await interaction.followup.send(
                f"❌ Erreur: Configuration du panneau Pterodactyl introuvable pour {server_name}.",
                ephemeral=True,
            )
            return

        try:
            api_client.client.servers.send_power_action(server_id, "start")
            await interaction.followup.send(
                f"✅ {server_name} démarré avec succès.", ephemeral=True
            )
        except Exception as e:
            print(f"Erreur lors du démarrage de {server_name}: {e}")
            await interaction.followup.send(
                f"❌ Échec du démarrage de {server_name}. Erreur: `{e}`", ephemeral=True
            )
        await self.cog.update_embed()

    @discord.ui.button(
        label="Redémarrer", style=discord.ButtonStyle.gray, custom_id="restart_button"
    )
    async def restart_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """
        Callback pour le bouton 'Redémarrer'.
        """
        await interaction.response.defer(ephemeral=True)
        server_name = self.cog.selected_server
        server_id = SERVERS[server_name]["id"]
        panel_key = SERVERS[server_name]["panel_key"]
        api_client = self.cog.pterodactyl_clients.get(panel_key)

        if not api_client:
            await interaction.followup.send(
                f"❌ Erreur: Configuration du panneau Pterodactyl introuvable pour {server_name}.",
                ephemeral=True,
            )
            return

        try:
            api_client.client.servers.send_power_action(server_id, "restart")
            await interaction.followup.send(
                f"🔄 {server_name} redémarré avec succès.", ephemeral=True
            )
        except Exception as e:
            print(f"Erreur lors du redémarrage de {server_name}: {e}")
            await interaction.followup.send(
                f"❌ Échec du redémarrage de {server_name}. Erreur: `{e}`",
                ephemeral=True,
            )
        await self.cog.update_embed()

    @discord.ui.button(
        label="Arrêter", style=discord.ButtonStyle.red, custom_id="stop_button"
    )
    async def stop_button_callback(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        """
        Callback pour le bouton 'Arrêter'.
        Gère le cas spécial pour "Lyxios Manage", qui est le bot lui-même.
        """
        await interaction.response.defer(ephemeral=True)
        server_name = self.cog.selected_server
        server_id = SERVERS[server_name]["id"]
        panel_key = SERVERS[server_name]["panel_key"]
        api_client = self.cog.pterodactyl_clients.get(panel_key)

        if not api_client:
            await interaction.followup.send(
                f"❌ Erreur: Configuration du panneau Pterodactyl introuvable pour {server_name}.",
                ephemeral=True,
            )
            return

        try:
            # CAS SPÉCIAL: Le serveur à arrêter est le bot lui-même.
            if server_name == "Lyxios Manage":
                # ÉTAPE 1: Mettre à jour l'embed pour afficher un statut "Hors ligne".
                # C'est la dernière action que le bot peut faire de manière fiable avant de s'éteindre.
                await interaction.followup.send(
                    f"🛑 {server_name} (le bot) va s'arrêter dans 3 secondes. L'embed sera mis à jour en 'Hors ligne'.",
                    ephemeral=True,
                )

                offline_embed = discord.Embed(
                    title="🔧 Système de Contrôle des Bots",
                    description=f"Le serveur **{server_name}** est en cours d'arrêt et sera bientôt hors ligne.",
                    color=discord.Color.red(),
                )
                offline_embed.add_field(
                    name="🔹 Bot sélectionné :", value=server_name, inline=False
                )
                offline_embed.add_field(
                    name="📡 Statut du serveur :",
                    value="🔴 Hors ligne (Pré-arrêt)",
                    inline=False,
                )
                now = discord.utils.utcnow()
                next_ping_time = now + datetime.timedelta(
                    seconds=30 - (now.second % 30)
                )
                next_update_timestamp = int(next_ping_time.timestamp())
                offline_embed.add_field(
                    name="S'actualise dans",
                    value=f"<t:{next_update_timestamp}:R>",
                    inline=False,
                )

                if self.cog.embed_message:
                    await self.cog.embed_message.edit(
                        embed=offline_embed, view=self.cog.view
                    )

                # ÉTAPE 2: Envoyer la commande d'arrêt au panneau Pterodactyl.
                # Après cette étape, le bot s'arrêtera et ne pourra plus exécuter de code.
                await asyncio.sleep(3)
                api_client.client.servers.send_power_action(server_id, "stop")
                print(
                    f"🛑 Commande d'arrêt envoyée à {server_name}. Le bot va maintenant s'éteindre."
                )

            # CAS GÉNÉRAL: Le serveur à arrêter est un autre bot/serveur.
            else:
                # ÉTAPE 1: Envoyer la commande d'arrêt.
                api_client.client.servers.send_power_action(server_id, "stop")
                await interaction.followup.send(
                    f"🛑 Commande d'arrêt envoyée à {server_name}.", ephemeral=True
                )

                # ÉTAPE 2: Mettre à jour l'embed pour refléter le nouveau statut (ex: "stopping").
                # C'est possible car le bot de contrôle lui-même reste en ligne.
                await self.cog.update_embed()

        except Exception as e:
            print(f"Erreur lors de la tentative d'arrêt de {server_name}: {e}")
            traceback.print_exc()
            await interaction.followup.send(
                f"❌ Échec de l'arrêt de {server_name}. Erreur: `{e}`", ephemeral=True
            )


# --- Cog Principal du Bot ---


class BotControl(commands.Cog):
    """
    Cog Discord pour le contrôle des serveurs Pterodactyl.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.selected_server = next(iter(SERVERS.keys()))
        self.embed_message = None
        self.channel_id = CHANNEL_ID
        self.message_id = (
            self._load_message_id()
        )  # Charge l'ID du message au démarrage du cog
        self.view = ServerControlView(self)  # Initialise la vue ici

        self.pterodactyl_clients = {}
        for key, config in PTERODACTYL_CONFIGS.items():
            api_key = config.get("api_key")
            if not api_key:
                print(
                    f"❌ Clé API manquante pour le panneau '{key}' dans la configuration PTERODACTYL_CONFIGS ou le fichier .env. Ce client ne sera pas initialisé."
                )
                continue  # Passe au client suivant

            try:
                self.pterodactyl_clients[key] = PterodactylClient(
                    url=config["url"], api_key=api_key
                )
                print(f"✅ Client Pterodactyl '{key}' initialisé.")
            except Exception as e:
                print(
                    f"❌ Erreur lors de l'initialisation du client Pterodactyl '{key}': {e}"
                )
                traceback.print_exc()

    def _load_message_id(self):
        """
        Charge l'ID du message depuis le fichier JSON.
        """
        if os.path.exists(MESSAGE_FILE):
            with open(MESSAGE_FILE) as f:
                try:
                    data = json.load(f)
                    loaded_id = data.get("message_id")
                    if loaded_id:
                        print(
                            f"📖 ID du message chargé depuis {MESSAGE_FILE}: {loaded_id}"
                        )
                    else:
                        print(
                            f"📖 Fichier {MESSAGE_FILE} trouvé, mais aucun ID de message valide à charger."
                        )
                    return loaded_id
                except json.JSONDecodeError:
                    print(
                        f"❌ Erreur de décodage JSON dans {MESSAGE_FILE}. Le fichier est peut-être corrompu. Retourne None."
                    )
                    return None
        print(f"📄 Fichier {MESSAGE_FILE} non trouvé. Aucun ID de message à charger.")
        return None

    def _save_message_id(self, message_id):
        """
        Sauvegarde l'ID du message dans le fichier JSON.
        """
        try:
            with open(MESSAGE_FILE, "w") as f:
                json.dump({"message_id": message_id}, f)
            print(f"💾 ID du message {message_id} sauvegardé dans {MESSAGE_FILE}.")
        except Exception as e:
            print(
                f"❌ Erreur lors de la sauvegarde de l'ID du message dans {MESSAGE_FILE}: {e}"
            )

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Exécuté lorsque le bot est prêt et connecté à Discord.
        """
        try:  # Added try-except block around the entire on_ready function
            print(
                "✅ Cog chargé et bot prêt. (Début on_ready)"
            )  # Modified print statement

            channel = self.bot.get_channel(self.channel_id)
            if not channel:
                print(
                    f"❌ Salon avec l'ID {self.channel_id} introuvable. Veuillez vérifier l'ID du salon."
                )
                return
            else:
                print(f"✅ Salon '{channel.name}' ({self.channel_id}) trouvé.")

            # Tente de récupérer le message d'embed existant en utilisant l'ID chargé
            if self.message_id:
                try:
                    self.embed_message = await channel.fetch_message(self.message_id)
                    print("✅ Message d'embed existant trouvé et récupéré avec succès.")
                except discord.NotFound:
                    print(
                        f"❌ Message d'embed avec l'ID {self.message_id} non trouvé dans le salon. Un nouveau message sera envoyé."
                    )
                    self.embed_message = None
                    self.message_id = (
                        None  # Réinitialise l'ID si le message n'est plus là
                    )
                    self._save_message_id(None)  # Efface l'ID invalide du fichier
                except discord.Forbidden:
                    print(
                        f"❌ Permissions insuffisantes pour récupérer le message d'embed avec l'ID {self.message_id}. Un nouveau message sera envoyé."
                    )
                    self.embed_message = None
                    self.message_id = (
                        None  # Réinitialise l'ID en cas de problème de permissions
                    )
                    self._save_message_id(None)  # Efface l'ID invalide du fichier
                except Exception as e:
                    print(
                        f"❌ Erreur inattendue lors de la récupération du message d'embed: {type(e).__name__}: {e}. Un nouveau message sera envoyé."
                    )
                    self.embed_message = None
                    self.message_id = None
                    self._save_message_id(None)
            else:
                print(
                    "ℹ️ Aucun ID de message précédemment enregistré ou valide. Un nouveau message sera envoyé."
                )
                self.embed_message = None

            print("⚙️ Avant d'ajouter la vue ServerControlView au bot.")  # New print
            self.bot.add_view(self.view)  # Utilise self.view
            print(
                "⚙️ Vue ServerControlView ajoutée au bot pour la persistance des interactions."
            )  # Existing print

            print(
                "🚦 Appel de update_embed pour la première fois..."
            )  # New print statement
            # Appelle update_embed pour la première fois.
            # Si embed_message est None, cela forcera l'envoi d'un nouveau message.
            await self.update_embed(first_time=(self.embed_message is None))

            self.check_server_status.start()

        except Exception as e:  # Catch any unexpected error in on_ready
            print(f"❌ Erreur critique dans on_ready: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()  # Print full traceback for debugging

    @tasks.loop(seconds=30)
    async def check_server_status(self):
        """
        Tâche en boucle pour vérifier et mettre à jour le statut du serveur toutes les 30 secondes.
        """
        await self.update_embed()

    async def update_embed(self, first_time=False):
        """
        Met à jour ou envoie un nouvel embed avec les informations du serveur.
        """
        channel = self.bot.get_channel(self.channel_id)
        if not channel:
            print(
                f"❌ Le salon avec l'ID {self.channel_id} est introuvable lors de la mise à jour de l'embed. Impossible de mettre à jour."
            )
            return

        server_name = self.selected_server
        server_config = SERVERS.get(server_name)

        if not server_config:
            print(
                f"❌ Erreur: Configuration du serveur '{server_name}' introuvable. Impossible de mettre à jour l'embed."
            )
            return

        server_id = server_config["id"]
        panel_key = SERVERS[server_name]["panel_key"]
        api_client = self.pterodactyl_clients.get(panel_key)

        node, status, cpu_usage, ram_usage, disk_usage = (
            "Inconnu",
            "🔴 Erreur de statut",
            "N/A",
            "N/A",
            "N/A",
        )
        error_message = None
        embed_color = discord.Color.greyple  # Couleur par défaut

        if not api_client:
            error_message = f"Client Pterodactyl pour '{panel_key}' non initialisé."
            print(f"❌ {error_message}")
            embed_color = discord.Color.red()
        else:
            try:
                server_info_raw = api_client.client.servers.get_server(server_id)
                server_stats_raw = api_client.client.servers.get_server_utilization(
                    server_id
                )

                server_info = (
                    server_info_raw if isinstance(server_info_raw, dict) else {}
                )
                server_stats = (
                    server_stats_raw if isinstance(server_stats_raw, dict) else {}
                )

                node = server_info.get("node", "Inconnu")

                state = server_stats.get("current_state", "unknown")
                if state == "running":
                    status = "🟢 En ligne"
                    embed_color = discord.Color.green()
                elif state == "starting":
                    status = "🟡 Démarrage..."
                    embed_color = discord.Color.gold()
                elif state == "stopping":
                    status = "🟠 Arrêt..."
                    embed_color = discord.Color.orange()
                else:
                    status = "🔴 Hors ligne"
                    embed_color = discord.Color.red()

                resources = server_stats.get("resources", {})
                cpu_usage = round(resources.get("cpu_absolute", 0), 2)
                ram_usage = round(resources.get("memory_bytes", 0) / (1024 * 1024), 2)
                disk_usage = round(resources.get("disk_bytes", 0) / (1024 * 1024), 2)

            except Exception as e:
                error_message = "Une erreur est survenue lors de la récupération des données du serveur."
                print(f"❌ {error_message} - Erreur: {e}")
                traceback.print_exc()  # Imprime la trace complète de l'erreur
                embed_color = discord.Color.red()

        embed = discord.Embed(
            title="🔧 Système de Contrôle des Bots", color=embed_color
        )
        embed.add_field(name="🔹 Bot sélectionné :", value=server_name, inline=False)
        embed.add_field(name="🆔 ID du serveur :", value=server_id, inline=False)
        embed.add_field(name="🖥️ Nœud :", value=node, inline=False)
        embed.add_field(name="📡 Statut du serveur :", value=status, inline=False)
        embed.add_field(name="🖥️ Utilisation CPU :", value=f"{cpu_usage}%", inline=True)
        embed.add_field(
            name="📂 Utilisation RAM :", value=f"{ram_usage} Mo", inline=True
        )
        embed.add_field(
            name="💾 Utilisation Disque :", value=f"{disk_usage} Mo", inline=True
        )

        if error_message:
            embed.add_field(name="⚠️ Erreur :", value=error_message, inline=False)
            # La couleur est déjà définie en rouge en cas d'erreur

        now = discord.utils.utcnow()
        # Calcul du timestamp pour la prochaine actualisation (arrondi aux 30 secondes les plus proches)
        next_ping_time = now + datetime.timedelta(seconds=30 - (now.second % 30))
        next_update_timestamp = int(next_ping_time.timestamp())

        embed.add_field(
            name="S'actualise dans",
            value=f"<t:{next_update_timestamp}:R>",
            inline=False,
        )
        embed.set_footer(
            text=f"Dernière mise à jour : {now.strftime('%H:%M:%S')} UTC"
        )  # Le footer est plus simple avec le champ

        view = self.view  # Utilise la vue persistante

        if first_time or self.embed_message is None:
            print(
                f"🚀 Tentative d'envoi d'un nouveau message d'embed dans le salon {channel.name} ({self.channel_id})."
            )
            try:
                message = await channel.send(embed=embed, view=view)
                self.embed_message = message
                self.message_id = message.id
                self._save_message_id(self.message_id)  # Sauvegarde le nouvel ID
                print(
                    f"✅ Nouveau message d'embed envoyé avec l'ID: {self.message_id}."
                )
            except Exception as e:
                print(
                    f"❌ Erreur critique lors de l'envoi du nouveau message d'embed dans le salon {channel.name} ({self.channel_id}): {type(e).__name__}: {e}"
                )
        else:
            try:
                await self.embed_message.edit(embed=embed, view=view)
            except discord.NotFound:
                print(
                    "❌ Le message d'embed à éditer n'a pas été trouvé. Envoi d'un nouveau message."
                )
                self.embed_message = None
                self.message_id = None
                self._save_message_id(None)
                await self.update_embed(first_time=True)
            except discord.Forbidden:
                print(
                    "❌ Permissions insuffisantes pour éditer le message d'embed. Envoi d'un nouveau message."
                )
                self.embed_message = None
                self.message_id = None
                self._save_message_id(None)
                await self.update_embed(first_time=True)
            except Exception as e:
                print(
                    f"❌ Erreur critique lors de l'édition du message d'embed: {type(e).__name__}: {e}"
                )


# --- Fonction de Setup pour le Cog ---


async def setup(bot: commands.Bot) -> None:
    """
    Fonction appelée par Discord.py pour ajouter le cog au bot.
    """
    await bot.add_cog(BotControl(bot))
