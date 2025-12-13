import asyncio
import concurrent.futures  # Pour exécuter des tâches de manière synchrone dans un thread séparé
import datetime
import logging
import os
import platform
import sys
from threading import Thread
import time
import traceback

import discord
from discord.ext import (
    commands,
    tasks,  # Importation de tasks pour les boucles
)
from dotenv import (
    load_dotenv,  # Utilisé pour charger les variables d'environnement (le token) depuis un fichier .env
)
from flask import Flask
import psutil
import pytz

import PARAM  # Importe les variables de configuration depuis le fichier PARAM.py

# Importation des cogs
EXTENSIONS = [
    "cog.statut",
    "cog.maj",  # Assure-toi que le chemin est correct (ex: 'cogs.maj' si c'est dans un dossier 'cogs')
]


logger = logging.getLogger()
logger.setLevel(logging.INFO)

for handler in logger.handlers[:]:
    logger.removeHandler(handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
)
logger.addHandler(console_handler)


logging.getLogger("discord").propagate = False
logging.getLogger("discord.http").propagate = False
logging.getLogger("aiohttp").propagate = False


# --- CONFIGURATION (chargée depuis PARAM.py) ---
BOT_ID = PARAM.BOT_ID
CHANNEL_ID = PARAM.CHANNEL_ID
# MESSAGE_ID n'est plus nécessaire ici, il est géré par panel.py
LOGS_CHANNEL_ID = PARAM.LOGS_CHANNEL_ID

# Définition des intentions pour le bot principal
# discord.Intents.all() est suffisant, mais si tu veux être plus précis:
intents = discord.Intents.default()
intents.message_content = True  # Nécessaire pour le contenu des messages si tu as des commandes préfixées qui en ont besoin
intents.guilds = (
    True  # Très important pour les commandes slash et les événements de guilde
)
intents.members = (
    True  # Si tu as besoin d'informations sur les membres (pour les commandes, etc.)
)
intents.presences = True  # Si tu veux surveiller les présences des membres (pour les commandes slash, etc.)

bot = commands.Bot(command_prefix="s%", intents=intents)


couleur = PARAM.couleur
owners = PARAM.owners
load_dotenv()  # Charge les variables du fichier .env
token = os.getenv("TOKEN")
# Récupère le token du bot depuis les variables d'environnement

tz = pytz.timezone("Europe/Paris")

previous_status = None


def is_owner(ctx) -> bool:  # N802: Function name `isOwner` should be lowercase
    return ctx.message.author.id in owners


@bot.command()
@commands.check(is_owner)
async def start(ctx, secondes=3) -> None:
    change_status.change_interval(seconds=secondes)


status_index = 0


@tasks.loop(seconds=5)
async def change_status() -> None:
    global status_index
    target_bot = bot.get_user(BOT_ID)
    statuses = [
        f"Je surveille {target_bot.name} !",
        "Le bot est hors ligne? Je te le dirais!",
    ]
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.CustomActivity(name=statuses[status_index]),
    )
    status_index = (status_index + 1) % len(statuses)


# ---------------------------------------------------------------------------------------------------------------
# ---------------------------------------------------------------------------------------------------------------
# ---------------------------------------------------------------------------------------------------------------

bot_start_time = datetime.datetime.now()

# Utilise un ThreadPoolExecutor pour les opérations bloquantes comme la taille des répertoires
executor = concurrent.futures.ThreadPoolExecutor()


def get_directory_size_bytes_sync(path) -> int:
    """Calcule la taille d'un répertoire de manière synchrone."""
    total_size = 0
    if not os.path.exists(path):
        return 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                if os.path.islink(
                    fp
                ):  # Évite de suivre les liens symboliques pour éviter les boucles infinies ou les erreurs
                    continue
                total_size += os.path.getsize(fp)
            except OSError as e:
                print(f"Erreur lors de la récupération de la taille de {fp}: {e}")
    return total_size


async def get_directory_size_async(path) -> int:
    """Exécute la fonction de taille de répertoire de manière asynchrone."""
    return await asyncio.get_running_loop().run_in_executor(
        executor, get_directory_size_bytes_sync, path
    )


def get_process_memory_mo() -> float:
    process = psutil.Process()
    mem_info = process.memory_info()
    return mem_info.rss / (1024**2)


def get_process_virtual_memory_mo() -> float:  # Nouvelle fonction
    process = psutil.Process()
    mem_info = process.memory_info()
    return mem_info.vms / (1024**2)


def get_process_cpu_usage() -> float:
    process = psutil.Process()
    # psutil.cpu_percent() peut retourner une valeur agrégée sur tous les cœurs,
    # ou pour le processus spécifique. Pour le processus, on appelle cpu_percent() sans intervalle
    # après un premier appel pour initialiser.
    process.cpu_percent(interval=None)  # Initialise le calcul
    time.sleep(0.1)  # Petite pause pour permettre la mesure
    return process.cpu_percent(interval=None)


# Nouvelle commande /ping
@bot.tree.command(name="ping", description="Affiche le ping du bot.")
async def ping_command(interaction: discord.Interaction) -> None:
    """Affiche la latence du bot."""
    # Latence WebSocket du bot vers Discord
    latency = round(bot.latency * 1000)

    # Mesure la latence aller-retour (Discord API -> Bot -> Discord API)
    start_time = datetime.datetime.now(datetime.UTC)
    # Utilise interaction.response.send_message pour la première réponse
    await interaction.response.send_message("Calcul de la latence...", ephemeral=True)
    # Puis utilise followup.send pour le message de ping réel pour mesurer le RTT
    message = await interaction.followup.send("Pinging...", ephemeral=True)
    end_time = datetime.datetime.now(datetime.UTC)

    # Supprime le message temporaire "Pinging..."
    await message.delete()

    full_circle_latency = round((end_time - start_time).total_seconds() * 1000)

    embed = discord.Embed(
        title="Latence du Bot",
        description=f"**Latence**\n> 📶 Latence WebSocket: {latency} ms\n> 🔄 Latence Aller-Retour (API): {full_circle_latency} ms",
        color=couleur,
    )
    # Modifie la réponse initiale avec l'embed final
    await interaction.edit_original_response("", embed=embed)


# Nouvelle commande /infos-tech
@bot.tree.command(
    name="infos-tech", description="Affiche les informations techniques du bot."
)
async def infos_tech_command(interaction: discord.Interaction) -> None:
    """Affiche diverses statistiques techniques du bot."""
    await interaction.response.defer(
        ephemeral=False
    )  # Déferre la réponse pour les calculs longs

    memory_usage = get_process_memory_mo()
    virtual_memory_usage = get_process_virtual_memory_mo()  # Nouvelle métrique
    cpu_percent = get_process_cpu_usage()

    # Calcul de l'espace disque de manière asynchrone
    bot_dir = "."
    data_dir_path = "data-base"  # Chemin relatif au répertoire du bot pour les données

    bot_disk_usage_octets = await get_directory_size_async(bot_dir)
    data_disk_usage_octets = await get_directory_size_async(data_dir_path)

    total_disk_usage_mo = round(
        (bot_disk_usage_octets + data_disk_usage_octets) / (1024**2), 2
    )

    # Correction pour la taille du cache: afficher le nombre de messages
    cached_messages_count = len(bot.cached_messages)

    # Convertir le temps de démarrage du bot en timestamp Unix
    # Le timestamp Discord est en secondes
    bot_start_unix_timestamp = int(bot_start_time.timestamp())
    # Formatage du timestamp Discord pour afficher la date et l'heure complètes (style 'F')
    uptime_discord_timestamp = f"<t:{bot_start_unix_timestamp}:F>"

    # Process start time
    process = psutil.Process()
    process_start_time = datetime.datetime.fromtimestamp(process.create_time())
    process_start_unix_timestamp = int(process_start_time.timestamp())

    discord_py_version = discord.__version__
    python_version = platform.python_version()

    servers = len(bot.guilds)
    # Calcul plus précis des utilisateurs en tenant compte des membres uniques si possible (nécessite l'intention MEMBERS)
    # Si l'intention MEMBERS n'est pas activée, sum(guild.member_count) est la meilleure estimation.
    users = sum(guild.member_count for guild in bot.guilds)

    app_command_count = len(bot.tree.get_commands())

    # Récupération des informations sur le système d'exploitation
    system_info = platform.system()
    release_info = platform.release()
    version_info = platform.version()
    processor_info = platform.processor()

    # Nouvelles métriques système
    logical_cores = psutil.cpu_count(logical=True)
    physical_cores = psutil.cpu_count(logical=False)

    total_disk_system = 0
    free_disk_system = 0
    try:
        disk_usage = psutil.disk_usage(".")
        total_disk_system = disk_usage.total / (1024**3)  # Convertir en Go
        free_disk_system = disk_usage.free / (1024**3)  # Convertir en Go
    except Exception as e:
        print(f"Erreur lors de la récupération de l'espace disque système: {e}")

    load_avg_str = "N/A (Windows)"
    if platform.system() == "Linux":
        try:
            load_avg = psutil.getloadavg()
            load_avg_1, load_avg_5, load_avg_15 = load_avg
            load_avg_str = f"{load_avg_1:.2f}, {load_avg_5:.2f}, {load_avg_15:.2f}"
        except Exception as e:
            print(f"Erreur lors de la récupération de la charge système: {e}")
            load_avg_str = "Erreur"

    linux_distro_info = "N/A"
    if platform.system() == "Linux":
        try:
            os_release = platform.freedesktop_os_release()
            linux_distro_info = (
                f"{os_release.get('NAME', 'N/A')} {os_release.get('VERSION', 'N/A')}"
            )
        except AttributeError:
            try:
                # platform.linux_distribution() est déprécié dans Python 3.8+
                # mais peut être utile pour la compatibilité avec des versions antérieures ou des environnements spécifiques.
                # Pour les versions de Python >= 3.8, il est préférable d'utiliser le module 'distro' (à installer séparément)
                # ou de parser /etc/os-release soi-même. Ici, on utilise la méthode native de platform si elle existe.
                linux_distro_info = " ".join(
                    filter(None, platform.linux_distribution())
                )  # filter(None) pour enlever les éléments vides
                if (
                    not linux_distro_info
                ):  # Si linux_distribution() retourne vide ou n'est pas dispo
                    linux_distro_info = (
                        "Impossible de récupérer la distribution Linux (fallback)"
                    )
            except Exception as e:
                print(
                    f"Erreur lors de la récupération de la distribution Linux (fallback): {e}"
                )
                linux_distro_info = "Erreur (fallback)"

    # Nouvelles métriques bot
    channels_count = sum(len(guild.channels) for guild in bot.guilds)
    roles_count = sum(len(guild.roles) for guild in bot.guilds)

    avg_shard_latency = "N/A (pas de sharding)"
    if bot.shard_count is not None and bot.shard_count > 0:
        total_latency_shards = 0
        for _, latency in bot.latencies:
            total_latency_shards += latency
        avg_shard_latency = f"{total_latency_shards / bot.shard_count * 1000:.2f} ms"
    else:
        avg_shard_latency = f"{round(bot.latency * 1000)} ms (sans sharding)"

    embed = discord.Embed(
        title="Informations Techniques du Bot",
        description=f"**Performance**\n"
        f"> 💾 Mémoire Utilisée (RSS): `{memory_usage:.2f} Mo`\n"
        f"> 📈 Mémoire Virtuelle (VMS): `{virtual_memory_usage:.2f} Mo`\n"  # Nouvelle ligne
        f"> 💻 Utilisation du CPU: `{cpu_percent:.2f}%`\n"
        f"> 📊 Charge Système (1, 5, 15 min): `{load_avg_str}`\n"  # Nouvelle ligne
        f"> 📁 Espace Disque du Bot: `{total_disk_usage_mo:.2f} Mo`\n\n"
        f"**Cache**\n"
        f"> ♻️ Messages mis en cache: `{cached_messages_count}`\n\n"
        f"**Uptime**\n"
        f"> 📊 En ligne depuis: {uptime_discord_timestamp}\n"
        f"> ⏰ Démarrage du Processus: <t:{process_start_unix_timestamp}:F>\n\n"  # Nouvelle ligne
        f"**Système**\n"
        f"> ⚙️ Système d'exploitation: `{system_info} {release_info} ({version_info})`\n"
        f"> 🧠 Processeur: `{processor_info}`\n"
        f"> ⚡️ Cœurs CPU (logiques/physiques): `{logical_cores}/{physical_cores}`\n"  # Nouvelle ligne
        f"> 🐧 Architecture: `{platform.architecture()[0]}`\n"
        f"> 🌐 Hostname: `{platform.node()}`\n"
        f"> 📦 Distribution Linux: `{linux_distro_info}`\n"  # Nouvelle ligne (si Linux)
        f"> 📊 Espace Disque Système (Total/Libre): `{total_disk_system:.2f} Go / {free_disk_system:.2f} Go`\n\n"  # Nouvelle ligne
        f"**Versions**\n"
        f"> 🐍 Version de Python: `{python_version}`\n"
        f"> 📚 Version de discord.py: `{discord_py_version}`\n\n"
        f"**Statistiques du Bot**\n"
        f"> 🌐 Serveurs: `{servers}`\n"
        f"> 👥 Utilisateurs: `{users}`\n"
        f"> 💬 Canaux: `{channels_count}`\n"  # Nouvelle ligne
        f"> 🎭 Rôles: `{roles_count}`\n"  # Nouvelle ligne
        f"> ✨ Commandes Slash: `{app_command_count}`\n"
        f"> 📶 Latence Moyenne Shards: `{avg_shard_latency}`",  # Mise à jour/Nouvelle ligne
        color=couleur,
    )
    embed.set_footer(
        text=f"Dernière mise à jour: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    await interaction.followup.send(embed=embed)


@bot.tree.command(
    name="sync",
    description="[🤖 Dev ] Recharge les extensions et synchronise les commandes slash.",
)
async def sync(interaction: discord.Interaction) -> None:
    await interaction.response.defer(
        ephemeral=True
    )  # Répondre immédiatement pour éviter le timeout
    # Vérifie si l'utilisateur est un propriétaire du bot
    if interaction.user.id in owners:
        await interaction.followup.send(
            "🔄 Démarrage de la synchronisation des commandes et du rechargement des extensions...",
            ephemeral=True,
        )
        try:
            # Décharger toutes les extensions avant de les recharger
            for extension in EXTENSIONS:
                try:
                    await bot.unload_extension(extension)
                except commands.ExtensionNotLoaded:
                    print(
                        f"Extension {extension} n'était pas chargée, pas besoin de la décharger."
                    )
                except Exception as e:
                    print(
                        f"Erreur lors du déchargement de l'extension {extension}: {e}"
                    )
                    await interaction.followup.send(
                        f"❌ Erreur lors du déchargement de l'extension {extension}: {e}",
                        ephemeral=True,
                    )
                    alert_id_owner = 946098490654740580  # Remplace par l'ID d'un propriétaire pour les alertes
                    owner_dm = await bot.fetch_user(alert_id_owner)
                    await owner_dm.send(
                        f"⚠️ Une erreur est survenue lors du déchargement de l'extension {extension}: {e}"
                    )
                    traceback.print_exc(file=sys.stderr)

            # Recharger chaque extension
            for extension in EXTENSIONS:
                try:
                    await bot.load_extension(extension)
                except Exception as e:
                    print(f"Erreur lors du chargement de l'extension {extension}: {e}")
                    await interaction.followup.send(
                        f"❌ Erreur lors du chargement de l'extension {extension}: {e}",
                        ephemeral=True,
                    )
                    alert_id_owner = 946098490654740580  # Remplace par l'ID d'un propriétaire pour les alertes
                    owner_dm = await bot.fetch_user(alert_id_owner)
                    await owner_dm.send(
                        f"⚠️ Une erreur est survenue lors du chargement de l'extension {extension}: {e}"
                    )
                    traceback.print_exc(file=sys.stderr)

            # Synchronise les commandes slash avec Discord
            synced = await bot.tree.sync()
            await interaction.followup.send(
                f"✅ Synchronisation complète. {len(synced)} commandes slash synchronisées et extensions rechargées.",
                ephemeral=True,
            )
            print(
                f"Synchronisation complète. {len(synced)} commandes slash synchronisées et extensions rechargées."
            )

            # Met à jour les fichiers JSON des commandes
            print("Données des commandes mises à jour.")

        except Exception as e:
            await interaction.followup.send(
                f"❌ Une erreur est survenue pendant la synchronisation : {e}",
                ephemeral=True,
            )
            print(f"Erreur globale pendant la synchronisation : {e}")
            traceback.print_exc(file=sys.stderr)
    else:
        await interaction.followup.send(
            "<:error2:1347966692915023952>・Vous devez faire partie du personnel de Lyxios pour pouvoir utiliser cette commande.",
            ephemeral=True,
        )


# ---------------------------------------------------------------------------------------------------------------
# ---------------------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------------------


def run_flask_server() -> None:
    flask_app = Flask(__name__)

    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)

    @flask_app.route("/")
    def home() -> tuple[str, int]:
        return "Manage Bot is alive!", 200

    try:
        flask_app.run(host="0.0.0.0", port=20170, debug=False)
    except Exception as e:
        print(f"Erreur lors du démarrage du serveur Flask : {e}")


@bot.event
async def on_ready() -> None:
    """
    Fonction on_ready principale du bot.
    Elle est appelée une fois que le bot est connecté à Discord.
    """
    # Cet on_ready est exécuté APRÈS que tous les cogs aient été chargés
    # et que le bot soit réellement prêt.
    print("Bot prêt")
    print("Bot running with:")
    print("Username: ", bot.user.name)
    print("User ID: ", bot.user.id)
    print("-------------------------")
    target_bot = bot.get_user(BOT_ID)
    if target_bot:
        print("Target Bot: ", target_bot.name)
    else:
        print(f"Target Bot: Introuvable (ID: {BOT_ID})")

    if not change_status.is_running():
        change_status.start()

    # Démarrer le serveur Flask dans un thread séparé
    server_thread = Thread(target=run_flask_server)
    server_thread.daemon = True
    server_thread.start()
    print("Serveur Flask démarré sur http://145.239.69.111:20170")

    # --- Synchronisation des commandes slash ici ---
    # Cette partie est cruciale pour que les commandes slash apparaissent
    try:
        # Synchronise toutes les commandes slash globales
        # Tu peux aussi synchroniser pour une guilde spécifique pour le développement rapide:
        synced = await bot.tree.sync()
        print(
            f"✅ Synchronisé {len(synced)} commandes slash globales après le démarrage."
        )
    except Exception as e:
        print(
            f"❌ Erreur lors de la synchronisation des commandes slash dans on_ready : {e}"
        )
        traceback.print_exc()


# --- Chargement des Cogs au démarrage ---
# Cette partie est exécutée avant que bot.run() ne bloque le thread
# et avant que l'événement on_ready ne soit déclenché par Discord.
async def main() -> None:
    # Charger les cogs
    for extension in EXTENSIONS:
        try:
            # Assure-toi que le chemin est correct. Si 'maj.py' est dans un dossier 'cog',
            # le nom de l'extension doit être 'cog.maj'.
            await bot.load_extension(extension)
            print(f"✅ Extension '{extension}' chargée avec succès.")
        except commands.ExtensionError as e:
            print(f"❌ Erreur lors du chargement de l'extension '{extension}': {e}")
            traceback.print_exc()
        except Exception as e:
            print(
                f"❌ Une erreur inattendue s'est produite lors du chargement de '{extension}': {e}"
            )
            traceback.print_exc()

    # Lancer le bot
    await bot.start(
        token
    )  # Utilisation de bot.start() pour un contrôle plus fin avec asyncio


if __name__ == "__main__":
    if token == "VOTRE_TOKEN_DISCORD_ICI" or not token:
        print(
            "❌ Erreur: Le token Discord n'est pas configuré. Veuillez le remplacer dans .env ou définir la variable d'environnement 'token'."
        )
    else:
        # Exécuter la fonction asynchrone main
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("Bot arrêté par l'utilisateur.")
        except Exception as e:
            print(f"❌ Erreur lors du démarrage du bot : {e}")
            traceback.print_exc()
