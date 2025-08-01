import discord
from discord.ext import commands, tasks
import datetime
import pytz
import asyncio
import logging
import PARAM # Importe les variables de configuration depuis le fichier PARAM.py

# Configuration du logger pour afficher les messages de rate limit
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('discord')

# --- CONFIGURATION (chargée depuis PARAM.py) ---
BOT_ID = PARAM.BOT_ID
CHANNEL_ID = PARAM.CHANNEL_ID
MESSAGE_ID = PARAM.MESSAGE_ID
LOGS_CHANNEL_ID = PARAM.LOGS_CHANNEL_ID
PING_ROLE_ID = PARAM.ROLE_ID

offline = PARAM.offline
online = PARAM.online

tz = pytz.timezone('Europe/Paris') # Définition du fuseau horaire

class Statut(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.BOT_ID = BOT_ID
        self.CHANNEL_ID = CHANNEL_ID
        self.MESSAGE_ID = MESSAGE_ID
        self.LOGS_CHANNEL_ID = LOGS_CHANNEL_ID
        self.PING_ROLE_ID = PING_ROLE_ID
        # Stocke le dernier statut connu (True pour online, False pour offline)
        self._last_known_status = None
        # Stocke le dernier titre d'embed affiché pour éviter les mises à jour redondantes d'embed
        self._last_embed_title = None
        # Lance la tâche de vérification du statut
        self.check_bot_status.start()

    def cog_unload(self):
        # Annule la tâche lorsque le cog est déchargé
        self.check_bot_status.cancel()

    async def _change_channel_name_with_retry(self, channel, new_name):
        """
        Tente de changer le nom du canal avec une gestion des rate limits,
        uniquement si le nom actuel est différent du nouveau nom.
        """
        if channel.name == new_name:
            # Le nom du canal est déjà correct, pas besoin de le changer
            log.debug(f"Nom du canal déjà '{new_name}'. Aucune modification nécessaire.")
            return True

        while True:
            try:
                await channel.edit(name=new_name)
                log.info(f"Nom du canal changé en '{new_name}'.")
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

    async def _send_and_delete_ping(self, channel, role_id, status_text=""):
        """
        Envoie un message avec une mention de rôle dans le canal spécifié,
        puis le supprime après un court délai.
        """
        try:
            # Le message de ping peut être générique ou inclure le statut
            ping_content = f"<@&{role_id}> Le bot vient de passer {status_text}." if status_text else f"<@&{role_id}> Un changement de statut du bot a eu lieu."
            ping_message = await channel.send(content=ping_content)
            await asyncio.sleep(2) # Attendre 2 secondes
            await ping_message.delete()
            log.info(f"Ping du rôle <@&{role_id}> envoyé et supprimé dans #{channel.name}.")
        except discord.HTTPException as e:
            log.error(f"Erreur HTTP lors de l'envoi/suppression du ping: {e}")
        except Exception as e:
            log.error(f"Erreur inattendue lors de l'envoi/suppression du ping: {e}")

    def _create_status_embed(self, is_online: bool, maj: str):
        """
        Crée et retourne un objet discord.Embed basé sur le statut.
        """
        if is_online:
            return discord.Embed(
                title=f"{online}・**Bot en ligne**",
                description=f"Le bot **Lyxios** est **en ligne** et toutes ses commandes et modules sont opérationnels !\n> Check ça pour savoir si le bot est `offline` avant que je le dise ! https://stats.uptimerobot.com/0izT1Nyywi .",
                color=0x00ff00
            ).set_footer(text=f"Mis à jour le: {maj}")
        else:
            return discord.Embed(
                title=f"{offline}・**Bot hors ligne**",
                description=f"Le bot **Lyxios** est **hors ligne**.\n\n> Ne vous inquiétez pas, le bot reviendra en ligne !\n> Check ça pour savoir si le bot est `online` avant que je le dise ! https://stats.uptimerobot.com/0izT1Nyywi\n-# Merci de votre patience.",
                color=0xff0000
            ).set_footer(text=f"Mis à jour le: {maj}")

    @tasks.loop(seconds=2) # Intervalle de 2 secondes
    async def check_bot_status(self):
        """
        Vérifie le statut du bot cible et met à jour le message et le nom du canal.
        Si le message n'est pas trouvé, il en crée un nouveau.
        """
        await self.bot.wait_until_ready() # Attend que le bot soit prêt

        channel = self.bot.get_channel(self.CHANNEL_ID)
        if not channel:
            log.error(f"Canal avec l'ID {self.CHANNEL_ID} introuvable. Veuillez vérifier l'ID dans PARAM.py.")
            return

        message = None
        # Cherche le bot cible dans les serveurs où le bot de surveillance est présent
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
            log.warning(f"Le bot cible avec l'ID {self.BOT_ID} n'a pas été trouvé dans les serveurs du bot actuel. Impossible de vérifier son statut. Assurez-vous que le bot cible est dans au moins un serveur commun.")

        try:
            message = await channel.fetch_message(self.MESSAGE_ID)
        except discord.NotFound:
            log.warning(f"Message avec l'ID {self.MESSAGE_ID} introuvable dans le canal {self.CHANNEL_ID}. Création d'un nouveau message.")
            maj = datetime.datetime.now(tz).strftime('%d/%m/%Y %H:%M:%S')
            new_embed = self._create_status_embed(is_target_bot_online, maj)
            try:
                new_message = await channel.send(embed=new_embed)
                self.MESSAGE_ID = new_message.id # Met à jour l'ID du message pour les futures mises à jour
                message = new_message # Utilise le nouveau message pour la suite de la logique
                log.info(f"Nouveau message de statut créé avec l'ID: {self.MESSAGE_ID}")
                
                # Met à jour le dernier statut et titre d'embed connu après la création
                # Sans envoyer de ping/log, car c'est une initialisation
                self._last_known_status = is_target_bot_online
                self._last_embed_title = new_embed.title
                
                # Le nom du canal doit être mis à jour même à la création si ce n'est pas déjà le cas
                channel_new_name = "═🟢・online" if is_target_bot_online else "═🔴・offline"
                await self._change_channel_name_with_retry(channel, channel_new_name)

                return # Sortir après la création et l'initialisation pour éviter les actions redondantes
            except discord.HTTPException as e:
                log.error(f"Erreur HTTP lors de la création du nouveau message: {e}")
                return
            except Exception as e:
                log.error(f"Erreur inattendue lors de la création du nouveau message: {e}")
                return
        except discord.Forbidden:
            log.error(f"Permissions insuffisantes pour récupérer le message dans le canal {self.CHANNEL_ID}. Le bot a-t-il les permissions de lecture de l'historique ?")
            return
        except Exception as e:
            log.error(f"Erreur inattendue lors de la récupération du message: {e}")
            return

        logs_channel = self.bot.get_channel(self.LOGS_CHANNEL_ID)
        if not logs_channel:
            log.warning(f"Canal de logs avec l'ID {self.LOGS_CHANNEL_ID} introuvable. Les messages de log ne seront pas envoyés.")

        # --- Début de la logique de vérification et de mise à jour ---

        # Si c'est la première exécution de la tâche et que le message existait déjà,
        # initialiser les états sans déclencher de notifications.
        if self._last_known_status is None:
            self._last_known_status = is_target_bot_online
            if message.embeds:
                self._last_embed_title = message.embeds[0].title
            log.info(f"Initialisation du statut connu du bot à {'en ligne' if is_target_bot_online else 'hors ligne'}.")
            return # Sortir pour éviter les actions sur la première itération (initialisation)

        maj = datetime.datetime.now(tz).strftime('%d/%m/%Y %H:%M:%S')
        new_embed = self._create_status_embed(is_target_bot_online, maj)
        
        # Détermine si une mise à jour est nécessaire
        # Une mise à jour est nécessaire si le statut a changé OU si l'embed affiché est incorrect
        needs_update = False
        if is_target_bot_online != self._last_known_status:
            needs_update = True
            log.debug(f"Statut du bot cible a changé de {'en ligne' if self._last_known_status else 'hors ligne'} à {'en ligne' if is_target_bot_online else 'hors ligne'}.")
        
        # Vérifie si l'embed affiché est incorrect, même si le statut n'a pas changé
        current_embed_title = message.embeds[0].title if message.embeds else None
        if current_embed_title != new_embed.title:
            needs_update = True
            log.info(f"Le titre de l'embed est incorrect (actuel: '{current_embed_title}', attendu: '{new_embed.title}'). Mise à jour forcée de l'embed.")

        if needs_update:
            # Mise à jour de l'embed
            try:
                await message.edit(content="", embed=new_embed)
                log.info(f"Embed du statut mis à jour pour le bot cible: {new_embed.title}")
                self._last_embed_title = new_embed.title # Met à jour le dernier titre d'embed connu
            except discord.HTTPException as e:
                log.error(f"Erreur HTTP lors de la mise à jour de l'embed du statut: {e}")
            except Exception as e:
                log.error(f"Erreur inattendue lors de la mise à jour de l'embed du statut: {e}")

            # Envoie le log
            if logs_channel:
                log_embed = self._create_status_embed(is_target_bot_online, maj)
                log_embed.title = f"{[online] if is_target_bot_online else [offline]}・Bot {'en ligne' if is_target_bot_online else 'hors ligne'}"
                log_embed.description = f"Le bot est **{'en ligne' if is_target_bot_online else 'hors ligne'}**"
                try:
                    await logs_channel.send(embed=log_embed)
                    log.info(f"Message de log envoyé: Bot {'en ligne' if is_target_bot_online else 'hors ligne'}")
                except discord.HTTPException as e:
                    log.error(f"Erreur HTTP lors de l'envoi du message de log: {e}")
                except Exception as e:
                    log.error(f"Erreur inattendue lors de l'envoi du message de log: {e}")

            # Gère le changement de nom du canal
            channel_new_name = "═🟢・online" if is_target_bot_online else "═🔴・offline"
            await self._change_channel_name_with_retry(channel, channel_new_name)

            # Mention
            await self._send_and_delete_ping(channel, self.PING_ROLE_ID, "en ligne" if is_target_bot_online else "hors ligne")

            # Met à jour le dernier statut connu après un changement
            self._last_known_status = is_target_bot_online
        else:
            log.debug(f"Le statut du bot cible n'a pas changé et l'embed est à jour ({'en ligne' if is_target_bot_online else 'hors ligne'}). Aucune mise à jour nécessaire.")


    @commands.command(name="s")
    @commands.is_owner() # Seuls les propriétaires peuvent utiliser cette commande
    async def set_statut(self, ctx, status: str):
        """
        Commande pour définir manuellement le statut du bot (online/offline).
        Ex: !s on
        """
        channel = self.bot.get_channel(self.CHANNEL_ID)
        if not channel:
            m_error = await ctx.send(f"Erreur: Canal avec l'ID {self.CHANNEL_ID} introuvable. Veuillez vérifier PARAM.py.", ephemeral=True)
            await asyncio.sleep(5)
            await m_error.delete()
            return

        message = None
        try:
            message = await channel.fetch_message(self.MESSAGE_ID)
        except discord.NotFound:
            m_error = await ctx.send(f"Erreur: Message avec l'ID {self.MESSAGE_ID} introuvable dans le canal {self.CHANNEL_ID}. Veuillez vérifier l'ID ou créer le message.", ephemeral=True)
            await asyncio.sleep(5)
            await m_error.delete()
            return
        except discord.Forbidden:
            m_error = await ctx.send(f"Erreur: Permissions insuffisantes pour récupérer le message dans le canal {self.CHANNEL_ID}.", ephemeral=True)
            await asyncio.sleep(5)
            await m_error.delete()
            return
        except Exception as e:
            m_error = await ctx.send(f"Erreur inattendue lors de la récupération du message: {e}", ephemeral=True)
            await asyncio.sleep(5)
            await m_error.delete()
            return

        logs_channel = self.bot.get_channel(self.LOGS_CHANNEL_ID)
        if not logs_channel:
            log.warning(f"Canal de logs avec l'ID {self.LOGS_CHANNEL_ID} introuvable. Les messages de log ne seront pas envoyés.")

        maj = datetime.datetime.now(tz).strftime('%d/%m/%Y %H:%M:%S')

        # Détermine le statut cible
        target_status_is_online = None
        if status.lower() == "on":
            target_status_is_online = True
        elif status.lower() == "off":
            target_status_is_online = False
        else:
            m3 = await ctx.send("Statut invalide. Veuillez utiliser `on` ou `off`.", ephemeral=True)
            await asyncio.sleep(5)
            await m3.delete()
            return

        new_embed = self._create_status_embed(target_status_is_online, maj)

        # Détermine si une mise à jour est nécessaire (statut différent ou embed incorrect)
        needs_update = False
        if target_status_is_online != self._last_known_status:
            needs_update = True
        
        # Si le statut n'a pas changé, vérifie si l'embed affiché est incorrect
        if not needs_update and message.embeds and message.embeds[0].title != new_embed.title:
            needs_update = True
            log.info(f"Le statut manuel est le même, mais le titre de l'embed est incorrect. Mise à jour forcée de l'embed.")

        if needs_update:
            # Effectue la mise à jour de l'embed si nécessaire
            if not message.embeds or message.embeds[0].title != new_embed.title:
                try:
                    await message.edit(content="", embed=new_embed)
                    log.info(f"Embed du statut mis à jour manuellement: {new_embed.title}")
                    self._last_embed_title = new_embed.title # Met à jour le dernier titre d'embed connu
                except discord.HTTPException as e:
                    await ctx.send(f"Erreur HTTP lors de la mise à jour manuelle de l'embed: {e}", ephemeral=True)
                    log.error(f"Erreur HTTP lors de la mise à jour manuelle de l'embed: {e}")
                except Exception as e:
                    await ctx.send(f"Erreur inattendue lors de la mise à jour manuelle de l'embed: {e}", ephemeral=True)
                    log.error(f"Erreur inattendue lors de la mise à jour manuelle de l'embed: {e}")
            else:
                log.debug(f"Le statut manuel est le même et l'embed est déjà correct ({new_embed.title}). Aucune mise à jour de l'embed nécessaire.")

            # Envoie le log si le statut a changé ou l'embed a été mis à jour
            if logs_channel and (target_status_is_online != self._last_known_status or (message.embeds and message.embeds[0].title != new_embed.title)):
                log_embed = self._create_status_embed(target_status_is_online, maj)
                log_embed.title = f"{[online] if target_status_is_online else [offline]}・Bot {'en ligne' if target_status_is_online else 'hors ligne'}"
                log_embed.description = f"Le bot est **{'en ligne' if target_status_is_online else 'hors ligne'}** (manuel)"
                try:
                    await logs_channel.send(embed=log_embed)
                    log.info(f"Message de log manuel envoyé: Bot {'en ligne' if target_status_is_online else 'hors ligne'}")
                except discord.HTTPException as e:
                    log.error(f"Erreur HTTP lors de l'envoi du message de log manuel: {e}")
                except Exception as e:
                    log.error(f"Erreur inattendue lors de l'envoi du message de log manuel: {e}")

            # Gère le changement de nom du canal
            channel_new_name = "═🟢・online" if target_status_is_online else "═🔴・offline"
            await self._change_channel_name_with_retry(channel, channel_new_name)

            # Mention quand le bot change de statut (manuellement)
            # ou si l'embed a été mis à jour après un statut inchangé mais un embed incorrect
            if target_status_is_online != self._last_known_status or (message.embeds and message.embeds[0].title != new_embed.title):
                await self._send_and_delete_ping(channel, self.PING_ROLE_ID, "en ligne" if target_status_is_online else "hors ligne")

            # Met à jour le dernier statut connu après un changement manuel
            self._last_known_status = target_status_is_online
            m = await ctx.send(f"Statut du bot mis à jour à `{status.lower()}`.", ephemeral=True)
            await asyncio.sleep(5)
            await m.delete()
        else:
            m = await ctx.send(f"Le statut du bot est déjà `{status.lower()}` et l'embed est à jour. Aucune mise à jour nécessaire.", ephemeral=True)
            await asyncio.sleep(5)
            await m.delete()


async def setup(bot):
    await bot.add_cog(Statut(bot))
