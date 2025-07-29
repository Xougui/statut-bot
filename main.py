import discord
import pytz
import datetime
import asyncio
import PARAM # Importe les variables de configuration depuis le fichier PARAM.py
import platform
import os
import psutil
import logging
from dotenv import load_dotenv # Utilisé pour charger les variables d'environnement (le token) depuis un fichier .env
from pydactyl import PterodactylClient # Peut être retiré si Panel.py gère tout
from discord.ext import commands
from discord import app_commands
from discord.ext import tasks # Importation de tasks pour les boucles
from flask import Flask
from threading import Thread
import sys
import traceback

# Importation des cogs
EXTENSIONS = [
    'cog.statut',
    'cog.panel',
    ]


logger = logging.getLogger()
logger.setLevel(logging.INFO)

for handler in logger.handlers[:]:
    logger.removeHandler(handler)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
logger.addHandler(console_handler)


logging.getLogger('discord').propagate = False
logging.getLogger('discord.http').propagate = False
logging.getLogger('aiohttp').propagate = False


# --- CONFIGURATION (chargée depuis PARAM.py) ---
BOT_ID = PARAM.BOT_ID
CHANNEL_ID = PARAM.CHANNEL_ID
# MESSAGE_ID n'est plus nécessaire ici, il est géré par panel.py
LOGS_CHANNEL_ID = PARAM.LOGS_CHANNEL_ID

intents = discord.Intents.all()

bot = commands.Bot(command_prefix='s%', intents=intents)



couleur = PARAM.couleur
owners = PARAM.owners
load_dotenv() # Charge les variables du fichier .env
token = os.getenv('token') # Récupère le token du bot depuis les variables d'environnement

tz = pytz.timezone('Europe/Paris')

previous_status = None

def isOwner(ctx):
    return ctx.message.author.id in owners

@bot.command()
@commands.check(isOwner)
async def start(ctx, secondes = 3):
    change_status.change_interval(seconds = secondes)

status_index = 0

@tasks.loop(seconds = 5)
async def change_status():
    global status_index
    target_bot = bot.get_user(BOT_ID)
    statuses = [f"Je surveille {target_bot.name} !", "Le bot est hors ligne? Je te le dirais!"]
    await bot.change_presence(status = discord.Status.online, activity=discord.CustomActivity(name=statuses[status_index]))
    status_index = (status_index + 1) % len(statuses)


#---------------------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------------

bot_start_time = datetime.datetime.now()

def get_directory_size_bytes(path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                total_size += os.path.getsize(fp)
            except OSError as e:
                print(f"Erreur lors de la récupération de la taille de {fp}: {e}")
    return total_size

def get_process_memory_mo():
    process = psutil.Process()
    mem_info = process.memory_info()
    return mem_info.rss / (1024 ** 2)

def get_process_cpu_usage():
    process = psutil.Process()
    return process.cpu_percent()

@bot.tree.command(name='ping-infos', description='Affiche le ping du bot et autres informations.')
async def ping(interaction: discord.Interaction):
    """Vérifie diverses statistiques du bot."""
    latency = round(bot.latency * 1000)
    memory_usage = get_process_memory_mo()
    cpu_percent = get_process_cpu_usage()

    bot_dir = "."
    data_dir = "../data"
    # Vérifier si le dossier 'data' existe, sinon, ajuster le chemin
    if not os.path.exists(data_dir):
        # Si 'data' n'est pas dans le dossier parent, il pourrait être dans le même dossier que le script
        data_dir = "./data"
        if not os.path.exists(data_dir):
            data_dir = None # Marquer comme non trouvé

    bot_disk_usage_octets = get_directory_size_bytes(bot_dir)
    data_disk_usage_octets = get_directory_size_bytes(data_dir) if data_dir else 0

    total_disk_usage_mo = round((bot_disk_usage_octets + data_disk_usage_octets) / (1024 ** 2), 2)

    cache_size = round(len(bot.cached_messages) / (1024 ** 2), 2)
    uptime_delta = datetime.datetime.now() - bot_start_time
    uptime_days, remainder = divmod(uptime_delta.total_seconds(), 86400)
    uptime_hours, remainder = divmod(remainder, 3600)
    uptime_minutes, uptime_seconds = divmod(remainder, 60)
    discord_py_version = discord.__version__
    python_version = platform.python_version()
    servers = len(bot.guilds)
    users = sum(guild.member_count for guild in bot.guilds)
    commands_to_exclude = ["help", "start"]
    prefix_commands = [cmd for cmd in bot.commands if cmd.name not in commands_to_exclude]
    command_count = len(prefix_commands) # Cette variable n'est pas utilisée dans l'embed final
    app_command_count = len(bot.tree.get_commands())
    start_time_ping = datetime.datetime.now(datetime.timezone.utc) # Renommé pour éviter conflit avec bot_start_time
    message = await interaction.channel.send('Pinging...')
    end_time_ping = datetime.datetime.now(datetime.timezone.utc) # Renommé
    await message.delete()
    full_circle_latency = round((end_time_ping - start_time_ping).total_seconds() * 1000)

    embed = discord.Embed(
        title='Statistiques du Bot',
        description=f'**Latence**\n> 📶 Latence: {latency} ms\n> 🔄 Latence Aller-Retour: {full_circle_latency} ms\n\n'
                    f'**Performance**\n> 💾 Mémoire Utilisée: {memory_usage:.2f} Mo\n'
                    f'> 💻 Utilisation du CPU: {cpu_percent}%\n'
                    f'> 📁 Espace Disque Total Estimé: {total_disk_usage_mo:.2f} Mo\n\n'
                    f'**Cache**\n> ♻️ Taille du Cache: {cache_size} Mo\n\n'
                    f'**Uptime**\n> 📊 En ligne depuis {int(uptime_days)} j, {int(uptime_hours)} h, {int(uptime_minutes)} min et {int(uptime_seconds)} sec\n\n'
                    f'**Système**\n> ⚙️ Version de discord.py: {discord_py_version}\n> ⚙️ Version de Python: {python_version}\n\n'
                    f'**Stats**\n> 🌐 Serveurs: {servers}\n> 💻 Utilisateurs: {users}\n'
                    f'> ✨ Commandes (Application): {app_command_count}',
        color=couleur
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="sync", description="[🤖 Dev ] Recharge les extensions et synchronise les commandes slash.")
async def sync(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)  # Répondre immédiatement pour éviter le timeout
    # Vérifie si l'utilisateur est un propriétaire du bot
    if interaction.user.id in owners:
        await interaction.followup.send("🔄 Démarrage de la synchronisation des commandes et du rechargement des extensions...", ephemeral=True)
        try:
            # Décharger toutes les extensions avant de les recharger
            for extension in EXTENSIONS:
                try:
                    await bot.unload_extension(extension)
                except commands.ExtensionNotLoaded:
                    print(f"Extension {extension} n'était pas chargée, pas besoin de la décharger.")
                except Exception as e:
                    print(f"Erreur lors du déchargement de l'extension {extension}: {e}")
                    await interaction.followup.send(f"❌ Erreur lors du déchargement de l'extension {extension}: {e}", ephemeral=True)
                    alert_id_owner = 946098490654740580
                    owner_dm = await bot.fetch_user(alert_id_owner)
                    await owner_dm.send(f"⚠️ Une erreur est survenue lors du déchargement de l'extension {extension}: {e}")
                    traceback.print_exc(file=sys.stderr)

            # Recharger chaque extension
            for extension in EXTENSIONS:
                try:
                    await bot.load_extension(extension)
                except Exception as e:
                    print(f"Erreur lors du chargement de l'extension {extension}: {e}")
                    await interaction.followup.send(f"❌ Erreur lors du chargement de l'extension {extension}: {e}", ephemeral=True)
                    alert_id_owner = 946098490654740580
                    owner_dm = await bot.fetch_user(alert_id_owner)
                    await owner_dm.send(f"⚠️ Une erreur est survenue lors du chargement de l'extension {extension}: {e}")
                    traceback.print_exc(file=sys.stderr)

            # Synchronise les commandes slash avec Discord
            synced = await bot.tree.sync()
            await interaction.followup.send(f"✅ Synchronisation complète. {len(synced)} commandes slash synchronisées et extensions rechargées.", ephemeral=True)
            print(f"Synchronisation complète. {len(synced)} commandes slash synchronisées et extensions rechargées.")

            # Met à jour les fichiers JSON des commandes
            print("Données des commandes mises à jour.")

        except Exception as e:
            await interaction.followup.send(f"❌ Une erreur est survenue pendant la synchronisation : {e}", ephemeral=True)
            print(f"Erreur globale pendant la synchronisation : {e}")
            traceback.print_exc(file=sys.stderr)
    else:
        await interaction.followup.send(f"<:error2:1347966692915023952>・Vous devez faire partie du personnel de Lyxios pour pouvoir utiliser cette commande.", ephemeral=True)

#---------------------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------------
#----------------------------------------------------------------------------------------------------------------


def run_flask_server():
    flask_app = Flask(__name__)

    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    @flask_app.route('/')
    def home():
        return "Manage Bot is alive!", 200

    try:
        flask_app.run(host='0.0.0.0', port=20170, debug=False)
    except Exception as e:
        print(f"Erreur lors du démarrage du serveur Flask : {e}")


@bot.event
async def on_ready():
    """
    Fonction on_ready principale du bot.
    Elle est appelée une fois que le bot est connecté à Discord.
    """
    # Cet on_ready est exécuté APRÈS que tous les cogs aient été chargés
    # et que le bot soit réellement prêt.
    print('Bot prêt')
    print("Bot running with:")
    print("Username: ", bot.user.name)
    print("User ID: ", bot.user.id)
    print("-------------------------")
    target_bot = bot.get_user(BOT_ID)
    if target_bot:
        print("Target Bot: ", target_bot.name)
    else:
        print("Target Bot: Introuvable (ID: {})".format(BOT_ID))

    if not change_status.is_running():
        change_status.start()

    # Démarrer le serveur Flask dans un thread séparé
    server_thread = Thread(target=run_flask_server)
    server_thread.daemon = True
    server_thread.start()
    print(f"Serveur Flask démarré sur http://145.239.69.111:20170")


# --- Chargement des Cogs au démarrage ---
# Cette partie est exécutée avant que bot.run() ne bloque le thread
# et avant que l'événement on_ready ne soit déclenché par Discord.
async def main():
    # Charger les cogs
    for extension in EXTENSIONS:
        try:
            await bot.load_extension(extension)
            print(f"✅ Extension '{extension}' chargée avec succès.")
        except commands.ExtensionError as e:
            print(f"❌ Erreur lors du chargement de l'extension '{extension}': {e}")
            traceback.print_exc()
        except Exception as e:
            print(f"❌ Une erreur inattendue s'est produite lors du chargement de '{extension}': {e}")
            traceback.print_exc()

    # Lancer le bot
    await bot.start(token) # Utilisation de bot.start() pour un contrôle plus fin avec asyncio

if __name__ == "__main__":
    if token == "VOTRE_TOKEN_DISCORD_ICI" or not token:
        print("❌ Erreur: Le token Discord n'est pas configuré. Veuillez le remplacer dans .env ou définir la variable d'environnement 'token'.")
    else:
        # Exécuter la fonction asynchrone main
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            None
        except Exception as e:
            print(f"❌ Erreur lors du démarrage du bot : {e}")
            traceback.print_exc()

