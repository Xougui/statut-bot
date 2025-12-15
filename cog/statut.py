import asyncio
from collections.abc import Callable
import contextlib
import datetime
from enum import Enum
import json
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks
import pytz

import PARAM

# --- Configuration du logging ---
log = logging.getLogger("discord")

# --- Constantes ---
BOT_ID = PARAM.BOT_ID
CHANNEL_ID = PARAM.CHANNEL_ID
LOGS_CHANNEL_ID = PARAM.LOGS_CHANNEL_ID
PING_ROLE_ID = PARAM.ROLE_ID

OFFLINE_EMOJI = PARAM.offline
ONLINE_EMOJI = PARAM.online
MAINTENANCE_EMOJI = PARAM.maintenance

COLOR_OFFLINE = 0xFF3131
COLOR_ONLINE = 0x00BF63
COLOR_MAINTENANCE = 0x004AAD

PARIS_TZ = pytz.timezone("Europe/Paris")
DATA_FILE = "data/statut.json"


class Status(Enum):
    """Énumération pour les statuts possibles."""

    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


def is_owner() -> Callable:
    """
    Vérifie si l'utilisateur qui exécute la commande est un propriétaire défini dans PARAM.owners.
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id not in PARAM.owners:
            await interaction.response.send_message(
                "Vous n'êtes pas autorisé à utiliser cette commande.", ephemeral=True
            )
            return False
        return True

    return app_commands.check(predicate)


class Statut(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._last_known_status: Status | None = None
        self._manual_reason: str | None = None
        self._update_lock = asyncio.Lock()
        self._message_id: int | None = None
        self._load_state()
        self._automatic_check_task.start()

    def cog_unload(self) -> None:
        self._automatic_check_task.cancel()

    # --- Gestion de l'état persistant ---

    def _load_state(self) -> None:
        """Charge l'ID du message depuis le fichier JSON."""
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                    self._message_id = data.get("message_id")
            except Exception as e:
                log.error(f"Erreur lors du chargement de {DATA_FILE}: {e}")
        else:
            log.info(f"{DATA_FILE} n'existe pas, il sera créé.")

    def _save_state(self) -> None:
        """Sauvegarde l'ID du message dans le fichier JSON."""
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({"message_id": self._message_id}, f, indent=4)
        except Exception as e:
            log.error(f"Erreur lors de la sauvegarde de {DATA_FILE}: {e}")

    # --- Fonctions d'analyse de statut ---

    def _get_status_from_embed(self, embed: discord.Embed | None) -> Status | None:
        """Détermine le statut à partir d'un embed."""
        if not embed or not embed.title:
            return None
        title = embed.title.lower()
        if "en ligne" in title or "online" in title:
            return Status.ONLINE
        if "hors ligne" in title or "offline" in title:
            return Status.OFFLINE
        if "en maintenance" in title or "maintenance" in title:
            return Status.MAINTENANCE
        return None

    def _get_status_from_channel_name(
        self, channel: discord.TextChannel | None
    ) -> Status | None:
        """Détermine le statut à partir du nom du salon."""
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

    # --- Fonctions de mise à jour de bas niveau ---

    async def _create_status_message(
        self, channel: discord.TextChannel
    ) -> discord.Message | None:
        """Crée un nouveau message de statut."""
        # On initialise avec un statut 'offline' par défaut pour commencer proprement
        embed = discord.Embed(
            title=f"{OFFLINE_EMOJI}・**Bot hors ligne**",
            description="Le bot **Lyxios** est **hors ligne**.\n\n> Ne vous inquiétez pas, le bot reviendra en ligne !\n> Check ça pour savoir si le bot est `online` avant que je le dise ! https://stats.uptimerobot.com/0izT1Nyywi\n-# Merci de votre patience.",
            color=COLOR_OFFLINE,
        )
        embed.set_footer(text="Initialisation du statut...")
        try:
            message = await channel.send(embed=embed)
            self._message_id = message.id
            self._save_state()
            log.info(f"Nouveau message de statut créé (ID: {message.id}).")
            return message
        except discord.HTTPException as e:
            log.error(f"Erreur lors de la création du message de statut: {e}")
            return None

    async def _update_embed(
        self, message: discord.Message, status: Status, reason: str | None = None
    ) -> bool:
        """Met à jour l'embed de statut."""
        maj = datetime.datetime.now(PARIS_TZ).strftime("%d/%m/%Y %H:%M:%S")

        embed_builders = {
            Status.ONLINE: lambda: discord.Embed(
                title=f"{ONLINE_EMOJI}・**Bot en ligne**",
                description="Le bot **Lyxios** est **en ligne** et toutes ses commandes et modules sont opérationnels !\n> Check ça pour savoir si le bot est `offline` avant que je le dise ! https://stats.uptimerobot.com/0izT1Nyywi .",
                color=COLOR_ONLINE,
            ),
            Status.OFFLINE: lambda: discord.Embed(
                title=f"{OFFLINE_EMOJI}・**Bot hors ligne**",
                description="Le bot **Lyxios** est **hors ligne**.\n\n> Ne vous inquiétez pas, le bot reviendra en ligne !\n> Check ça pour savoir si le bot est `online` avant que je le dise ! https://stats.uptimerobot.com/0izT1Nyywi\n-# Merci de votre patience.",
                color=COLOR_OFFLINE,
            ),
            Status.MAINTENANCE: lambda: discord.Embed(
                title=f"{MAINTENANCE_EMOJI}・**Bot en maintenance**",
                description="Le bot **Lyxios** est actuellement en **maintenance**.\n\n> Il sera de retour dès que possible. Merci de votre compréhension.",
                color=COLOR_MAINTENANCE,
            ),
        }
        builder = embed_builders.get(status)
        if not builder:
            return False

        embed = builder()
        if reason:
            embed.description += f"\n\n**Raison:** {reason}"

        new_embed = embed.set_footer(text=f"Mis à jour le: {maj}")
        try:
            await message.edit(embed=new_embed)
            log.info(f"Embed de statut mis à jour à: {status.name}")
            return True
        except discord.HTTPException as e:
            log.error(f"Erreur HTTP lors de la mise à jour de l'embed: {e}")
            return False

    async def _update_channel_name(
        self,
        channel: discord.TextChannel,
        status: Status,
        interaction: discord.Interaction | None = None,
        progress_log: list[str] | None = None,
    ) -> bool:
        """Met à jour le nom du salon."""
        name_map = {
            Status.ONLINE: "🟢・online",
            Status.OFFLINE: "🔴・offline",
            Status.MAINTENANCE: "🔵・maintenance",
        }
        new_name = name_map.get(status)
        if not new_name or channel.name == new_name:
            return True

        try:
            await channel.edit(name=new_name)
            log.info(f"Nom du salon changé en '{new_name}'.")
            return True
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = e.retry_after or 5.0
                log.warning(f"Rate limited (channel name): waiting {retry_after:.2f}s.")
                if interaction and progress_log is not None:
                    try:
                        progress_log.append(
                            f"⏳ Nom du salon rate limited. Réessai dans {retry_after:.2f}s..."
                        )
                        await interaction.edit_original_response(
                            content="\n".join(progress_log)
                        )
                    except discord.HTTPException:
                        pass
                await asyncio.sleep(retry_after)
                if interaction and progress_log is not None:
                    with contextlib.suppress(IndexError):
                        progress_log.pop()
                # On pourrait ré-essayer ici, mais la boucle s'en chargera
                return False
            elif e.status == 403:
                log.error("Erreur 403 (Permissions) pour changer le nom du salon.")
                return False
            else:
                log.error(f"Erreur HTTP ({e.status}) en changeant le nom du salon: {e}")
                return False
        except Exception as e:
            log.error(f"Erreur inattendue en changeant le nom du salon: {e}")
            return False

    async def _send_log(
        self,
        logs_channel: discord.TextChannel,
        status: Status,
        manual: bool,
        reason: str | None = None,
    ) -> bool:
        """Envoie un log dans le salon dédié."""
        emoji_map = {
            Status.ONLINE: ONLINE_EMOJI,
            Status.OFFLINE: OFFLINE_EMOJI,
            Status.MAINTENANCE: MAINTENANCE_EMOJI,
        }

        color_map = {
            Status.ONLINE: COLOR_ONLINE,
            Status.OFFLINE: COLOR_OFFLINE,
            Status.MAINTENANCE: COLOR_MAINTENANCE,
        }

        log_embed = discord.Embed(
            title=f"{emoji_map.get(status)}・Bot {status.value}",
            description=f"Le bot est maintenant **{status.value}**.",
            color=color_map.get(status, COLOR_OFFLINE),
        )
        if manual:
            log_embed.description += " (défini manuellement)"
        if reason:
            log_embed.description += f"\n**Raison:** {reason}"

        try:
            await logs_channel.send(embed=log_embed)
            log.info(f"Message de log envoyé pour le statut {status.name}.")
            return True
        except discord.HTTPException as e:
            log.error(f"Erreur HTTP lors de l'envoi du log: {e}")
            return False

    async def _send_ping(self, channel: discord.TextChannel, status: Status) -> bool:
        """Envoie un ping temporaire."""
        if status == Status.MAINTENANCE:
            return True
        try:
            ping_message = await channel.send(
                content=f"<@&{PING_ROLE_ID}> Le bot vient de passer {status.value}."
            )
            await asyncio.sleep(2)
            await ping_message.delete()
            log.info(f"Ping du rôle <@&{PING_ROLE_ID}> envoyé et supprimé.")
            return True
        except discord.HTTPException as e:
            log.error(f"Erreur HTTP lors de l'envoi/suppression du ping: {e}")
            return False

    # --- Tâche de vérification et de mise à jour ---

    @tasks.loop(seconds=5)
    async def _automatic_check_task(self) -> None:
        """Tâche de fond qui appelle la logique de mise à jour principale."""
        await self._update_status_logic()

    async def _get_target_status(self) -> Status | None:
        """Détermine le statut cible en fonction de l'état du bot surveillé."""
        # Si on surveille le bot lui-même
        if self.bot.user.id == BOT_ID:
            # On considère qu'il est ONLINE si le code tourne
            # (Sauf si on implémente une logique spécifique)
            return Status.ONLINE

        # Sinon on cherche le membre dans les serveurs communs
        target_bot_member = None
        for guild in self.bot.guilds:
            member = guild.get_member(BOT_ID)
            if member:
                target_bot_member = member
                break

        if not target_bot_member:
            # On ne trouve pas le bot -> warning mais on ne peut rien dire
            # Ou on considère OFFLINE ?
            # Pour l'instant on log juste
            return None

        return (
            Status.ONLINE
            if target_bot_member.status != discord.Status.offline
            else Status.OFFLINE
        )

    async def _update_status_logic(
        self,
        interaction: discord.Interaction | None = None,
        forced_status: Status | None = None,
        reason: str | None = None,
    ) -> None:
        async with self._update_lock:
            progress_log = []
            is_interactive = interaction is not None

            if is_interactive and interaction:
                status_msg = forced_status.value if forced_status else "auto"
                if reason:
                    status_msg += f" (Raison: {reason})"
                progress_log.append(
                    f"⏳ **Mise à jour vers `{status_msg}` en cours...**"
                )
                with contextlib.suppress(discord.InteractionResponded):
                    await interaction.edit_original_response(
                        content="\n".join(progress_log)
                    )

            # 1. Déterminer le statut cible
            is_manual = forced_status is not None
            if is_manual and forced_status:
                target_status = forced_status
            else:
                target_status_detected = await self._get_target_status()
                if target_status_detected is None:
                    # On n'a pas pu déterminer le statut cible (bot introuvable)
                    # On garde l'ancien ou on ne fait rien
                    if is_interactive and interaction:
                        await interaction.followup.send(
                            "⚠️ Impossible de trouver le bot cible.", ephemeral=True
                        )
                    return
                target_status = target_status_detected

            # 2. Récupérer les indicateurs visuels
            channel = self.bot.get_channel(CHANNEL_ID)
            if not channel or not isinstance(channel, discord.TextChannel):
                log.error(
                    f"Salon de statut (ID: {CHANNEL_ID}) introuvable ou invalide."
                )
                if is_interactive and interaction:
                    await interaction.followup.send(
                        "❌ Salon de statut introuvable.", ephemeral=True
                    )
                return

            message = None
            if self._message_id:
                try:
                    message = await channel.fetch_message(self._message_id)
                except (discord.NotFound, discord.Forbidden):
                    log.warning(
                        f"Message de statut (ID: {self._message_id}) introuvable. Création d'un nouveau..."
                    )
                    message = None

            if not message:
                message = await self._create_status_message(channel)
                if not message:
                    if is_interactive and interaction:
                        await interaction.followup.send(
                            "❌ Impossible de créer le message de statut.",
                            ephemeral=True,
                        )
                    return

            embed_status = self._get_status_from_embed(
                message.embeds[0] if message.embeds else None
            )

            name_status = self._get_status_from_channel_name(channel)

            # 3. Comparer et agir
            status_has_changed = (
                self._last_known_status is not None
                and target_status != self._last_known_status
            )
            embed_is_inconsistent = embed_status != target_status
            name_is_inconsistent = name_status != target_status

            if (
                not status_has_changed
                and not embed_is_inconsistent
                and not name_is_inconsistent
                and not is_manual
            ):
                if is_interactive and interaction:
                    await interaction.edit_original_response(
                        content="✅ Tout est déjà à jour."
                    )
                return

            # Actions de mise à jour
            if embed_is_inconsistent or is_manual:
                if await self._update_embed(message, target_status, reason=reason):
                    if is_interactive and interaction:
                        progress_log.append("✅ Message de statut mis à jour.")
                        await interaction.edit_original_response(
                            content="\n".join(progress_log)
                        )
                elif is_interactive and interaction:
                    progress_log.append("❌ Échec de la mise à jour du message.")
                    await interaction.edit_original_response(
                        content="\n".join(progress_log)
                    )

            if name_is_inconsistent or is_manual:
                if await self._update_channel_name(
                    channel,
                    target_status,
                    interaction,
                    progress_log if is_interactive else None,
                ):
                    if is_interactive and interaction:
                        progress_log.append("✅ Nom du salon mis à jour.")
                        await interaction.edit_original_response(
                            content="\n".join(progress_log)
                        )
                elif is_interactive and interaction:
                    progress_log.append("❌ Échec de la mise à jour du nom du salon.")
                    await interaction.edit_original_response(
                        content="\n".join(progress_log)
                    )

            # Actions de notification (uniquement si le statut change)
            if status_has_changed or (
                is_manual and target_status != self._last_known_status
            ):
                logs_channel = self.bot.get_channel(LOGS_CHANNEL_ID)
                if isinstance(logs_channel, discord.TextChannel) and (
                    await self._send_log(
                        logs_channel, target_status, manual=is_manual, reason=reason
                    )
                    and is_interactive
                    and interaction
                ):
                    progress_log.append("📄 Message de log envoyé.")
                    await interaction.edit_original_response(
                        content="\n".join(progress_log)
                    )

                if (
                    await self._send_ping(channel, target_status)
                    and is_interactive
                    and interaction
                ):
                    progress_log.append("🔔 Notification envoyée.")
                    await interaction.edit_original_response(
                        content="\n".join(progress_log)
                    )

            self._last_known_status = target_status

            if is_interactive and interaction:
                progress_log.append("\n🎉 Opération terminée.")
                await interaction.edit_original_response(
                    content="\n".join(progress_log)
                )

    async def _check_ids(self) -> None:
        """Vérifie la validité des IDs configurés au démarrage."""
        # Check Channel
        channel = self.bot.get_channel(CHANNEL_ID)
        if not channel:
            log.error(
                f"❌ CHANNEL_ID invalide: Impossible de trouver le salon avec l'ID {CHANNEL_ID}."
            )
        elif not isinstance(channel, discord.TextChannel):
            log.error(
                f"❌ CHANNEL_ID invalide: L'ID {CHANNEL_ID} ne correspond pas à un salon textuel."
            )
        else:
            log.info(f"✅ CHANNEL_ID valide: {channel.name} ({channel.guild.name})")

            # Check Role (dependant on channel guild)
            role = channel.guild.get_role(PING_ROLE_ID)
            if not role:
                log.warning(
                    f"⚠️ ROLE_ID introuvable: Le rôle avec l'ID {PING_ROLE_ID} n'existe pas dans le serveur {channel.guild.name}."
                )
            else:
                log.info(f"✅ ROLE_ID valide: {role.name}")

        # Check Logs Channel
        logs_channel = self.bot.get_channel(LOGS_CHANNEL_ID)
        if not logs_channel:
            log.warning(
                f"⚠️ LOGS_CHANNEL_ID introuvable: Impossible de trouver le salon avec l'ID {LOGS_CHANNEL_ID}."
            )
        elif not isinstance(logs_channel, discord.TextChannel):
            log.warning(
                f"⚠️ LOGS_CHANNEL_ID invalide: L'ID {LOGS_CHANNEL_ID} ne correspond pas à un salon textuel."
            )
        else:
            log.info(
                f"✅ LOGS_CHANNEL_ID valide: {logs_channel.name} ({logs_channel.guild.name})"
            )

        # Check Bot ID
        if self.bot.user.id == BOT_ID:
            log.info("✅ BOT_ID valide: Le bot se surveille lui-même.")
        else:
            found = False
            for guild in self.bot.guilds:
                if guild.get_member(BOT_ID):
                    found = True
                    break
            if found:
                log.info(
                    "✅ BOT_ID valide: Bot cible trouvé dans les serveurs communs."
                )
            else:
                log.warning(
                    f"⚠️ BOT_ID introuvable: Impossible de trouver le membre avec l'ID {BOT_ID} dans les serveurs communs."
                )

    @_automatic_check_task.before_loop
    async def before_check(self) -> None:
        await self.bot.wait_until_ready()

        await self._check_ids()

        # On essaie d'initialiser le statut connu à partir du message existant
        if self._message_id:
            channel = self.bot.get_channel(CHANNEL_ID)
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(self._message_id)
                    self._last_known_status = self._get_status_from_embed(
                        message.embeds[0] if message.embeds else None
                    )
                    if self._last_known_status:
                        log.info(
                            f"Statut initialisé à partir du message existant : {self._last_known_status.name}"
                        )
                except (discord.NotFound, discord.Forbidden):
                    log.warning(
                        f"Message de statut (ID: {self._message_id}) non trouvé lors de l'initialisation. Un nouveau sera créé."
                    )
                    # On ne crée pas le message tout de suite, la boucle le fera
                    self._message_id = None
                    self._save_state()

    # --- Commande manuelle ---

    @app_commands.command(name="statut", description="[🤖 Dev] Gère le statut du bot.")
    @app_commands.describe(
        mode="Choisissez un mode manuel ou revenez à l'automatique.",
        raison="Raison optionnelle pour le changement de statut (s'affiche dans l'embed).",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="🟢 Online", value="online"),
            app_commands.Choice(name="🔴 Offline", value="offline"),
            app_commands.Choice(name="🔵 Maintenance", value="maintenance"),
            app_commands.Choice(name="🤖 Automatique", value="automatique"),
        ]
    )
    @is_owner()
    async def set_status_slash(
        self,
        interaction: discord.Interaction,
        mode: app_commands.Choice[str],
        raison: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        if mode.value == "automatique":
            self._manual_reason = None
            if not self._automatic_check_task.is_running():
                self._automatic_check_task.start()
                log.info("Tâche de vérification automatique redémarrée.")
            await self._update_status_logic(interaction=interaction)
        else:
            self._manual_reason = raison
            if self._automatic_check_task.is_running():
                self._automatic_check_task.cancel()
                log.info(
                    "Tâche de vérification automatique mise en pause (mode manuel activé)."
                )

            target_status = Status(mode.value)
            await self._update_status_logic(
                interaction=interaction, forced_status=target_status, reason=raison
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Statut(bot))
