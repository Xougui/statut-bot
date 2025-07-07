import discord
from discord.ext import commands, tasks
import datetime
import pytz
import asyncio
import logging
import PARAM

# Configuration du logger pour afficher les messages de rate limit
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('discord')

# Importation des variables globales depuis PARAM.py
BOT_ID = PARAM.BOT_ID
CHANNEL_ID = PARAM.CHANNEL_ID
MESSAGE_ID = PARAM.MESSAGE_ID
LOGS_CHANNEL_ID = PARAM.LOGS_CHANNEL_ID
owners = PARAM.owners  # Liste des IDs des propriétaires du bot

tz = pytz.timezone('Europe/Paris') # Définition du fuseau horaire

class Statut(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.BOT_ID = BOT_ID
        self.CHANNEL_ID = CHANNEL_ID
        self.MESSAGE_ID = MESSAGE_ID
        self.LOGS_CHANNEL_ID = LOGS_CHANNEL_ID
        self.check_bot_status.start() # Lance la tâche de vérification du statut

    def cog_unload(self):
        self.check_bot_status.cancel() # Annule la tâche lorsque le cog est déchargé

    async def _change_channel_name_with_retry(self, channel, new_name):
        """
        Tente de changer le nom du canal avec une gestion des rate limits.
        """
        while True:
            try:
                await channel.edit(name=new_name)
                return True # Succès
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = e.retry_after if e.retry_after else 5 # Utilise retry_after ou une valeur par défaut
                    log.warning(f"Rate limited lors du changement de nom du canal. Réessai dans {retry_after:.2f} secondes.")
                    await asyncio.sleep(retry_after)
                else:
                    log.error(f"Erreur HTTP lors du changement de nom du canal: {e}")
                    return False # Échec pour une autre raison
            except Exception as e:
                log.error(f"Erreur inattendue lors du changement de nom du canal: {e}")
                return False

    @tasks.loop(seconds=2) # Intervalle de 2 secondes
    async def check_bot_status(self):
        """
        Vérifie le statut du bot cible et met à jour le message et le nom du canal.
        """
        await self.bot.wait_until_ready() # Attend que le bot soit prêt

        channel = self.bot.get_channel(self.CHANNEL_ID)
        if not channel:
            log.error(f"Canal avec l'ID {self.CHANNEL_ID} introuvable.")
            return

        message = None
        try:
            message = await channel.fetch_message(self.MESSAGE_ID)
        except discord.NotFound:
            log.error(f"Message avec l'ID {self.MESSAGE_ID} introuvable dans le canal {self.CHANNEL_ID}.")
            return
        except discord.Forbidden:
            log.error(f"Permissions insuffisantes pour récupérer le message dans le canal {self.CHANNEL_ID}.")
            return
        except Exception as e:
            log.error(f"Erreur lors de la récupération du message: {e}")
            return

        logs_channel = self.bot.get_channel(self.LOGS_CHANNEL_ID)

        # Cherche le bot cible dans les serveurs où Lyxios est présent
        target_bot_member = None
        for guild in self.bot.guilds:
            target_bot_member = guild.get_member(self.BOT_ID)
            if target_bot_member:
                break

        is_target_bot_online = False
        if target_bot_member:
            # Si le membre est trouvé, vérifie son statut
            is_target_bot_online = target_bot_member.status != discord.Status.offline
        else:
            log.warning(f"Le bot cible avec l'ID {self.BOT_ID} n'a pas été trouvé dans les serveurs du bot actuel. Impossible de vérifier son statut.")
            # Si le bot cible n'est pas trouvé, on considère qu'il est hors ligne pour la mise à jour du statut.

        maj = datetime.datetime.now(tz).strftime('%d/%m/%Y %H:%M:%S')

        # Vérifie si le bot cible est en ligne
        if is_target_bot_online:
            # Bot cible en ligne
            if "🔴" in channel.name or "offline" in channel.name:
                # Si le canal indique hors ligne, le met à jour
                embed = discord.Embed(title="<a:online:1346871720845348864>・**Bot en ligne**", description=f"Le bot **Lyxios** est **en ligne** et toutes ses commandes et modules sont opérationnels !\n> Check ça pour savoir si le bot est `offline` avant que je le dise ! https://stats.uptimerobot.com/0izT1Nyywi .", color=0x00ff00)
                embed.set_footer(text=f"Mis à jour le: {maj}")
                await message.edit(content="", embed=embed)

                if logs_channel:
                    embed_logs = discord.Embed(title="<a:online:1346871720845348864>・**Bot en ligne**", description="Le bot est **en ligne**", color=0x00ff00)
                    embed_logs.set_footer(text=f"Mis à jour le: {maj}")
                    await logs_channel.send(embed=embed_logs)

                await self._change_channel_name_with_retry(channel, "═🟢・online")
        else:
            # Bot cible hors ligne
            if "🟢" in channel.name or "online" in channel.name:
                # Si le canal indique en ligne, le met à jour
                embed = discord.Embed(title="<a:offline:1346871717938729062>・**Bot hors ligne**", description=f"Le bot **Lyxios** est **hors ligne**.\n\n> Ne vous inquiétez pas, le bot reviendra en ligne !\n> Check ça pour savoir si le bot est `online` avant que je le dise ! https://stats.uptimerobot.com/0izT1Nyywi\n-# Merci de votre patience.", color=0xff0000)
                embed.set_footer(text=f"Mis à jour le: {maj}")
                await message.edit(content="", embed=embed)

                if logs_channel:
                    embed_logs = discord.Embed(title="<a:offline:1346871717938729062>・**Bot hors ligne**", description="Le bot est **hors ligne**", color=0xff0000)
                    embed_logs.set_footer(text=f"Mis à jour le: {maj}")
                    await logs_channel.send(embed=embed_logs)
                
                # Envoi d'un ping et suppression après un court délai
                ping = await channel.send(content="<@&1350429004032770068>")
                await asyncio.sleep(1)
                await ping.delete()

                await self._change_channel_name_with_retry(channel, "═🔴・offline")


    @commands.command(name="s")
    @commands.is_owner() # Seuls les propriétaires peuvent utiliser cette commande
    async def set_statut(self, ctx, status: str):
        """
        Commande pour définir manuellement le statut du bot (online/offline).
        Ex: !statut online
        """
        channel = self.bot.get_channel(self.CHANNEL_ID)
        if not channel:
            m_error = await ctx.send(f"Canal avec l'ID {self.CHANNEL_ID} introuvable.", ephemeral=True)
            await asyncio.sleep(5)
            await m_error.delete()
            return

        message = None
        try:
            message = await channel.fetch_message(self.MESSAGE_ID)
        except discord.NotFound:
            m_error = await ctx.send(f"Message avec l'ID {self.MESSAGE_ID} introuvable dans le canal {self.CHANNEL_ID}.", ephemeral=True)
            await asyncio.sleep(5)
            await m_error.delete()
            return
        except discord.Forbidden:
            m_error = await ctx.send(f"Permissions insuffisantes pour récupérer le message dans le canal {self.CHANNEL_ID}.", ephemeral=True)
            await asyncio.sleep(5)
            await m_error.delete()
            return
        except Exception as e:
            m_error = await ctx.send(f"Erreur lors de la récupération du message: {e}", ephemeral=True)
            await asyncio.sleep(5)
            await m_error.delete()
            return

        logs = self.bot.get_channel(self.LOGS_CHANNEL_ID)
        maj = datetime.datetime.now(tz).strftime('%d/%m/%Y %H:%M:%S')

        status_changed = False # Pour éviter les messages redondants

        if status.lower() == "on":
            if "🔴" in channel.name or "offline" in channel.name:
                embed = discord.Embed(title="<a:online:1346871720845348864>・**Bot en ligne**", description=f"Le bot **Lyxios** est **en ligne** et toutes ses commandes et modules sont opérationnels !\n> Check ça pour savoir si le bot est `offline` avant que je le dise ! https://stats.uptimerobot.com/0izT1Nyywi .", color=0x00ff00)
                embed.set_footer(text=f"Mis à jour le: {maj}")
                await message.edit(content="", embed=embed)

                if logs:
                    embed_logs = discord.Embed(title="<a:online:1346871720845348864>・**Bot en ligne**", description="Le bot est **en ligne**", color=0x00ff00)
                    embed_logs.set_footer(text=f"Mis à jour le: {maj}")
                    await logs.send(embed=embed_logs)

                await self._change_channel_name_with_retry(channel, "═🟢・online")
                status_changed = True
            else:
                m2 = await ctx.send("Le bot est déjà affiché comme étant en ligne.", ephemeral=True)
                await asyncio.sleep(5)
                await m2.delete()
        elif status.lower() == "off":
            if "🟢" in channel.name or "online" in channel.name:
                embed = discord.Embed(title="<a:offline:1346871717938729062>・**Bot hors ligne**", description=f"Le bot **Lyxios** est **hors ligne**.\n\n> Ne vous inquiétez pas, le bot reviendra en ligne !\n> Check ça pour savoir si le bot est `online` avant que je le dise ! https://stats.uptimerobot.com/0izT1Nyywi\n-# Merci de votre patience.", color=0xff0000)
                embed.set_footer(text=f"Mis à jour le: {maj}")
                await message.edit(content="", embed=embed)

                if logs:
                    embed_logs = discord.Embed(title="<a:offline:1346871717938729062>・**Bot hors ligne**", description="Le bot est **hors ligne**", color=0xff0000)
                    embed_logs.set_footer(text=f"Mis à jour le: {maj}")
                    await logs.send(embed=embed_logs)

                ping = await channel.send(content="<@&1350429004032770068>")
                await asyncio.sleep(1)
                await ping.delete()
                
                await self._change_channel_name_with_retry(channel, "═🔴・offline")
                status_changed = True
            else:
                m2 = await ctx.send("Le bot est déjà affiché comme étant hors ligne.", ephemeral=True)
                await asyncio.sleep(5)
                await m2.delete()
        else:
            m3 = await ctx.send("Statut invalide. Veuillez utiliser `online` ou `offline`.", ephemeral=True)
            await asyncio.sleep(5)
            await m3.delete()

        if status_changed:
            m = await ctx.send(f"Statut du bot mis à jour à `{status.lower()}`.", ephemeral=True)
            await asyncio.sleep(5)
            await m.delete()

async def setup(bot):
    await bot.add_cog(Statut(bot))
