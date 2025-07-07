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
from discord.ext import tasks, commands
from flask import Flask
from threading import Thread

# Importation des cogs
EXTENSIONS = [
    'cog.statut'
    ]

# --- CONFIGURATION (chargée depuis PARAM.py) ---
BOT_ID = PARAM.BOT_ID
CHANNEL_ID = PARAM.CHANNEL_ID
MESSAGE_ID = PARAM.MESSAGE_ID
LOGS_CHANNEL_ID = PARAM.LOGS_CHANNEL_ID

intents = discord.Intents.all()
intents.presences = True
bot = commands.Bot(command_prefix='s%', intents=intents)

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

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
    command_count = len(prefix_commands)
    app_command_count = len(bot.tree.get_commands())
    start_time = datetime.datetime.now(datetime.timezone.utc)
    message = await interaction.channel.send('Pinging...')
    end_time = datetime.datetime.now(datetime.timezone.utc)
    await message.delete()
    full_circle_latency = round((end_time - start_time).total_seconds() * 1000)

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
    
#---------------------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------------
#----------------------------------------------------------------------------------------------------------------


def run_flask_server():
    flask_app = Flask(__name__)

    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    @flask_app.route('/')
    def home():
        return "Bot is alive!", 200

    try:
        flask_app.run(host='0.0.0.0', port=6198, debug=False)
    except Exception as e:
        print(f"Erreur lors du démarrage du serveur Flask : {e}")


@bot.event
async def on_ready():
    if not change_status.is_running():
        change_status.start()
    target_bot = bot.get_user(BOT_ID)
    print('Bot prêt')
    print("Bot running with:")
    print("Username: ", bot.user.name)
    print("User ID: ", bot.user.id)
    print("-------------------------")
    print("Target Bot: ", target_bot.name)
    
    # Charger les cogs depuis la liste EXTENSIONS
    for extension in EXTENSIONS:
        try:
            await bot.load_extension(extension)
            print(f"✅ Extension '{extension}' chargée avec succès.")
        except commands.ExtensionError as e:
            print(f"❌ Erreur lors du chargement de l'extension '{extension}': {e}")
        except Exception as e:
            print(f"❌ Une erreur inattendue s'est produite lors du chargement de '{extension}': {e}")

    # Démarrer le serveur Flask dans un thread séparé
    server_thread = Thread(target=run_flask_server)
    server_thread.daemon = True
    server_thread.start()
    print(f"Serveur Flask démarré sur http://0.0.0.0:6198")

bot.run(token)