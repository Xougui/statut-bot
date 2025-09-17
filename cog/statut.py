import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import pytz
import asyncio
import logging
from enum import Enum

import PARAM

# --- Configuration du logging ---
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('discord')

# --- Constantes ---
BOT_ID = PARAM.BOT_ID
CHANNEL_ID = PARAM.CHANNEL_ID
MESSAGE_ID = PARAM.MESSAGE_ID
LOGS_CHANNEL_ID = PARAM.LOGS_CHANNEL_ID
PING_ROLE_ID = PARAM.ROLE_ID

OFFLINE_EMOJI = PARAM.offline
ONLINE_EMOJI = PARAM.online
MAINTENANCE_EMOJI = PARAM.maintenance

COLOR_OFFLINE = 0xFF3131
COLOR_ONLINE = 0x00BF63
COLOR_MAINTENANCE = 0x004AAD

PARIS_TZ = pytz.timezone('Europe/Paris')

# --- Énumération pour les statuts possibles ---
class Status(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"

class Statut(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_known_status: Status | None = None
        self._manual_status_override = False
        self._update_lock = asyncio.Lock()
        self.check_bot_status.start()

    def cog_unload(self):
        self.check_bot_status.cancel()

    # --- Fonctions d'analyse de statut ---

    def _get_status_from_embed(self, embed: discord.Embed | None) -> Status | None:
        """Analyse un embed pour en extraire le statut."""
        if not embed or not embed.title:
            return None
        title = embed.title.lower()
        if "en ligne" in title:
            return Status.ONLINE
        if "hors ligne" in title:
            return Status.OFFLINE
        if "en maintenance" in title:
            return Status.MAINTENANCE
        return None

    def _get_status_from_channel_name(self, channel: discord.TextChannel | None) -> Status | None:
        """Analyse le nom d'un salon pour en extraire le statut."""
        if not channel:
            return None
        name = channel.name.lower()
        if "online" in name or "🟢" in name:
            return Status.ONLINE
        if "offline" in name or "🔴" in name:
            return Status.OFFLINE
        if "maintenance" in name or "🔵" in name:
            return Status.MAINTENANCE
        return None

    # --- Fonctions de mise à jour individuelles ---

    async def _update_embed(self, message: discord.Message, status: Status) -> bool:
        """Met à jour l'embed du message de statut."""
        maj = datetime.datetime.now(PARIS_TZ).strftime('%d/%m/%Y %H:%M:%S')

        embed_builders = {
            Status.ONLINE: lambda: discord.Embed(
                title=f"{ONLINE_EMOJI}・**Bot en ligne**",
                description=f"Le bot **Lyxios** est **en ligne** et toutes ses commandes et modules sont opérationnels !\n> Check ça pour savoir si le bot est `offline` avant que je le dise ! https://stats.uptimerobot.com/0izT1Nyywi .",
                color=COLOR_ONLINE
            ),
            Status.OFFLINE: lambda: discord.Embed(
                title=f"{OFFLINE_EMOJI}・**Bot hors ligne**",
                description=f"Le bot **Lyxios** est **hors ligne**.\n\n> Ne vous inquiétez pas, le bot reviendra en ligne !\n> Check ça pour savoir si le bot est `online` avant que je le dise ! https://stats.uptimerobot.com/0izT1Nyywi\n-# Merci de votre patience.",
                color=COLOR_OFFLINE
            ),
            Status.MAINTENANCE: lambda: discord.Embed(
                title=f"{MAINTENANCE_EMOJI}・**Bot en maintenance**",
                description=f"Le bot **Lyxios** est actuellement en **maintenance**.\n\n> Il sera de retour dès que possible. Merci de votre compréhension.",
                color=COLOR_MAINTENANCE
            ),
        }

        builder = embed_builders.get(status)
        if not builder: return False

        new_embed = builder().set_footer(text=f"Mis à jour le: {maj}")

        try:
            await message.edit(embed=new_embed)
            log.info(f"Embed de statut mis à jour à: {status.name}")
            return True
        except discord.HTTPException as e:
            log.error(f"Erreur HTTP lors de la mise à jour de l'embed: {e}")
            return False

    async def _update_channel_name(self, channel: discord.TextChannel, status: Status, interaction: discord.Interaction | None = None, progress_log: list | None = None) -> bool:
        """Met à jour le nom du salon de statut avec gestion des rate limits et feedback optionnel."""
        name_map = {
            Status.ONLINE: "═🟢・online",
            Status.OFFLINE: "═🔴・offline",
            Status.MAINTENANCE: "═🔵・maintenance",
        }
        new_name = name_map.get(status)

        if not new_name or channel.name == new_name:
            return True

        while True:
            try:
                await channel.edit(name=new_name)
                log.info(f"Nom du salon changé en '{new_name}'.")
                return True
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = e.retry_after or 5.0
                    log.warning(f"Rate limited (channel name): waiting {retry_after:.2f}s.")
                    if interaction and progress_log:
                        try:
                            progress_log.append(f"⏳ Nom du salon rate limited. Réessai dans {retry_after:.2f}s...")
                            await interaction.edit_original_response(content="\n".join(progress_log))
                        except discord.HTTPException: pass

                    await asyncio.sleep(retry_after)

                    if interaction and progress_log:
                        try:
                            progress_log.pop()
                        except IndexError: pass
                elif e.status == 403:
                    log.error("Erreur 403 (Permissions) pour changer le nom du salon.")
                    return False
                else:
                    log.error(f"Erreur HTTP ({e.status}) en changeant le nom du salon: {e}")
                    return False
            except Exception as e:
                log.error(f"Erreur inattendue en changeant le nom du salon: {e}")
                return False

    async def _send_log(self, logs_channel: discord.TextChannel, status: Status, manual: bool):
        """Envoie un message de log pour le changement de statut."""
        emoji_map = { Status.ONLINE: ONLINE_EMOJI, Status.OFFLINE: OFFLINE_EMOJI, Status.MAINTENANCE: MAINTENANCE_EMOJI }
        log_embed = discord.Embed(
            title=f"{emoji_map.get(status)}・Bot {status.value}",
            description=f"Le bot est maintenant **{status.value}**.",
            color=COLOR_ONLINE if status == Status.ONLINE else COLOR_OFFLINE if status == Status.OFFLINE else COLOR_MAINTENANCE
        )
        if manual:
            log_embed.description += " (défini manuellement)"
        try:
            await logs_channel.send(embed=log_embed)
            log.info(f"Message de log envoyé pour le statut {status.name}.")
            return True
        except discord.HTTPException as e:
            log.error(f"Erreur HTTP lors de l'envoi du log: {e}")
            return False

    async def _send_ping(self, channel: discord.TextChannel, status: Status):
        """Envoie une mention de rôle temporaire, sauf pour la maintenance."""
        if status == Status.MAINTENANCE:
            log.debug("Ping ignoré pour le statut de maintenance.")
            return True
        try:
            ping_content = f"<@&{PING_ROLE_ID}> Le bot vient de passer {status.value}."
            ping_message = await channel.send(content=ping_content)
            await asyncio.sleep(2)
            await ping_message.delete()
            log.info(f"Ping du rôle <@&{PING_ROLE_ID}> envoyé et supprimé.")
            return True
        except discord.HTTPException as e:
            log.error(f"Erreur HTTP lors de l'envoi/suppression du ping: {e}")
            return False

    # --- Tâche de vérification principale ---

    @tasks.loop(seconds=5)
    async def check_bot_status(self, interaction: discord.Interaction | None = None) -> list[str]:
        """
        Tâche principale qui vérifie et corrige l'état du bot et des indicateurs visuels.
        Fournit un retour progressif si un objet 'interaction' est passé.
        Retourne une liste de chaînes décrivant les actions entreprises.
        """
        async with self._update_lock:
            actions_taken = []
            progress_log = []

            if interaction:
                progress_log.append("⚙️ Vérification en cours...")
                await interaction.edit_original_response(content="\n".join(progress_log))

            await self.bot.wait_until_ready()

            target_bot_member = next((g.get_member(BOT_ID) for g in self.bot.guilds if g.get_member(BOT_ID)), None)
            if not target_bot_member:
                log.warning(f"Bot cible (ID: {BOT_ID}) introuvable.")
                return actions_taken

            current_status = Status.ONLINE if target_bot_member.status != discord.Status.offline else Status.OFFLINE

            channel = self.bot.get_channel(CHANNEL_ID)
            if not channel:
                log.error(f"Canal de statut (ID: {CHANNEL_ID}) introuvable.")
                return actions_taken

            try:
                message = await channel.fetch_message(MESSAGE_ID)
                embed_status = self._get_status_from_embed(message.embeds[0] if message.embeds else None)
            except (discord.NotFound, discord.Forbidden) as e:
                log.error(f"Impossible de récupérer le message de statut (ID: {MESSAGE_ID}). Erreur: {e}")
                return actions_taken

            name_status = self._get_status_from_channel_name(channel)

            status_has_changed = self._last_known_status is not None and current_status != self._last_known_status
            embed_is_inconsistent = embed_status != current_status
            name_is_inconsistent = name_status != current_status

            if not status_has_changed and not embed_is_inconsistent and not name_is_inconsistent:
                if interaction: await interaction.edit_original_response(content="✅ Tout est déjà à jour.")
                return actions_taken

            if embed_is_inconsistent:
                log.info(f"Correction de l'embed (attendu: {current_status.name}, vu: {embed_status}).")
                if await self._update_embed(message, current_status):
                    actions_taken.append("✅ Message de statut mis à jour.")
                    if interaction:
                        progress_log.append(actions_taken[-1])
                        await interaction.edit_original_response(content="\n".join(progress_log))

            if name_is_inconsistent:
                log.info(f"Correction du nom du salon (attendu: {current_status.name}, vu: {name_status}).")
                if await self._update_channel_name(channel, current_status, interaction, progress_log):
                    actions_taken.append("✅ Nom du salon mis à jour.")
                    if interaction:
                        progress_log.append(actions_taken[-1])
                        await interaction.edit_original_response(content="\n".join(progress_log))

            if status_has_changed:
                log.info(f"Changement de statut détecté: {self._last_known_status.name} -> {current_status.name}")
                if logs_channel := self.bot.get_channel(LOGS_CHANNEL_ID):
                    if await self._send_log(logs_channel, current_status, manual=False):
                        actions_taken.append("📄 Message de log envoyé.")
                        if interaction:
                            progress_log.append(actions_taken[-1])
                            await interaction.edit_original_response(content="\n".join(progress_log))
                if await self._send_ping(channel, current_status):
                    actions_taken.append("🔔 Notification envoyée.")
                    if interaction:
                        progress_log.append(actions_taken[-1])
                        await interaction.edit_original_response(content="\n".join(progress_log))

            self._last_known_status = current_status

            if interaction:
                progress_log.append("\n🎉 Vérification terminée.")
                await interaction.edit_original_response(content="\n".join(progress_log))

            return actions_taken

    @check_bot_status.before_loop
    async def before_check(self):
        """Initialise l'état interne du bot en lisant le message de statut existant."""
        await self.bot.wait_until_ready()
        log.info("Initialisation du statut avant le démarrage de la boucle...")

        channel = self.bot.get_channel(CHANNEL_ID)
        if not channel:
            log.error(f"Canal de statut (ID: {CHANNEL_ID}) introuvable.")
            return

        try:
            message = await channel.fetch_message(MESSAGE_ID)
            self._last_known_status = self._get_status_from_embed(message.embeds[0] if message.embeds else None)
            if self._last_known_status:
                log.info(f"Statut initialisé à partir du message existant : {self._last_known_status.name}")
            else:
                log.warning("Impossible d'initialiser le statut depuis l'embed existant.")
        except (discord.NotFound, discord.Forbidden):
            log.warning(f"Message de statut (ID: {MESSAGE_ID}) non trouvé/accessible pour l'initialisation.")

    # --- Commande manuelle ---

    @app_commands.command(name="statut", description="[🤖 Dev] Gère le statut du bot.")
    @app_commands.describe(mode="Choisissez un mode manuel ou revenez à l'automatique.")
    @app_commands.choices(mode=[
        app_commands.Choice(name="🟢 Online", value="online"),
        app_commands.Choice(name="🔴 Offline", value="offline"),
        app_commands.Choice(name="🛠️ Maintenance", value="maintenance"),
        app_commands.Choice(name="⚙️ Automatique", value="automatique"),
    ])
    @commands.is_owner()
    async def set_status_slash(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        """Définit manuellement le statut ou revient en mode automatique."""
        await interaction.response.defer(ephemeral=True)

        if mode.value == "automatique":
            self._manual_status_override = False
            if not self.check_bot_status.is_running():
                self.check_bot_status.start()
                log.info("Tâche de vérification automatique redémarrée.")

            # La fonction check_bot_status gère maintenant elle-même le retour progressif
            # lorsqu'on lui passe l'objet interaction.
            await self.check_bot_status(interaction=interaction)
            return

        # --- Passage en mode manuel ---
        self._manual_status_override = True
        if self.check_bot_status.is_running():
            self.check_bot_status.cancel()
            log.info("Tâche de vérification automatique mise en pause (mode manuel activé).")

        target_status = Status(mode.value)
        if target_status == self._last_known_status:
            await interaction.followup.send(f"Le bot est déjà en mode `{target_status.value}`.", ephemeral=True)
            return

        channel = self.bot.get_channel(CHANNEL_ID)
        if not channel:
            await interaction.followup.send(f"❌ Erreur: Canal de statut (ID: {CHANNEL_ID}) introuvable.", ephemeral=True)
            return
        
        try:
            message = await channel.fetch_message(MESSAGE_ID)
        except (discord.NotFound, discord.Forbidden):
            await interaction.followup.send(f"❌ Erreur: Message de statut (ID: {MESSAGE_ID}) introuvable.", ephemeral=True)
            return

        progress = [f"⏳ **Passage en mode manuel : `{target_status.value}`...**"]
        await interaction.edit_original_response(content="\n".join(progress))

        if await self._update_embed(message, target_status):
            progress.append("✅ Message de statut mis à jour.")
        else: progress.append("❌ Échec de la mise à jour du message.")
        await interaction.edit_original_response(content="\n".join(progress))

        if await self._update_channel_name(channel, target_status, interaction=interaction, progress_log=progress):
            progress.append("✅ Nom du salon mis à jour.")
        else: progress.append("❌ Échec de la mise à jour du nom du salon.")
        await interaction.edit_original_response(content="\n".join(progress))

        if logs_channel := self.bot.get_channel(LOGS_CHANNEL_ID):
            if await self._send_log(logs_channel, target_status, manual=True):
                progress.append("✅ Message de log envoyé.")
            else: progress.append("❌ Échec de l'envoi du log.")
            await interaction.edit_original_response(content="\n".join(progress))

        if await self._send_ping(channel, target_status):
            progress.append("✅ Notification envoyée.")
        else: progress.append("❌ Échec de l'envoi de la notification.")

        progress.append(f"\n🎉 **Terminé !** Statut réglé sur `{target_status.value}`.")
        await interaction.edit_original_response(content="\n".join(progress))

        self._last_known_status = target_status
        log.info(f"Statut manuel défini sur: {target_status.name}")

async def setup(bot):
    await bot.add_cog(Statut(bot))
