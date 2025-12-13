import asyncio
import contextlib
import datetime
from enum import Enum
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks
import pytz

import PARAM

# --- Configuration du logging ---
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("discord")

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

PARIS_TZ = pytz.timezone("Europe/Paris")


# --- Énumération pour les statuts possibles ---
class Status(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class Statut(commands.Cog):
    def __init__(self, bot) -> None:
        self.bot = bot
        self._last_known_status: Status | None = None
        self._manual_reason: str | None = None
        self._update_lock = asyncio.Lock()
        self._automatic_check_task.start()

    def cog_unload(self) -> None:
        self._automatic_check_task.cancel()

    # --- Fonctions d'analyse de statut ---

    def _get_status_from_embed(self, embed: discord.Embed | None) -> Status | None:
        if not embed or not embed.title:  # E701
            return None
        title = embed.title.lower()
        if "en ligne" in title:  # E701
            return Status.ONLINE
        if "hors ligne" in title:  # E701
            return Status.OFFLINE
        if "en maintenance" in title:  # E701
            return Status.MAINTENANCE
        return None

    def _get_status_from_channel_name(
        self, channel: discord.TextChannel | None
    ) -> Status | None:
        if not channel:  # E701
            return None
        name = channel.name.lower()
        if "online" in name or "🟢" in name:  # E701
            return Status.ONLINE
        if "offline" in name or "🔴" in name:  # E701
            return Status.OFFLINE
        if "maintenance" in name or "🔵" in name:  # E701
            return Status.MAINTENANCE
        return None

    # --- Fonctions de mise à jour de bas niveau ---

    async def _update_embed(
        self, message: discord.Message, status: Status, reason: str | None = None
    ) -> bool:
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
        if not builder:  # E701
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
        progress_log: list | None = None,
    ) -> bool:
        name_map = {
            Status.ONLINE: "═🟢・online",
            Status.OFFLINE: "═🔴・offline",
            Status.MAINTENANCE: "═🔵・maintenance",
        }
        new_name = name_map.get(status)
        if not new_name or channel.name == new_name:  # E701
            return True
        while True:
            try:
                await channel.edit(name=new_name)
                log.info(f"Nom du salon changé en '{new_name}'.")
                return True
            except discord.HTTPException as e:
                if e.status == 429:
                    retry_after = e.retry_after or 5.0
                    log.warning(
                        f"Rate limited (channel name): waiting {retry_after:.2f}s."
                    )
                    if interaction and progress_log:
                        try:
                            progress_log.append(
                                f"⏳ Nom du salon rate limited. Réessai dans {retry_after:.2f}s..."
                            )
                            await interaction.edit_original_response(
                                content="\n".join(progress_log)
                            )
                        except discord.HTTPException:  # E701
                            pass
                    await asyncio.sleep(retry_after)
                    if interaction and progress_log:
                        with contextlib.suppress(
                            IndexError
                        ):  # E701: Multiple statements on one line (colon)
                            progress_log.pop()
                elif e.status == 403:
                    log.error("Erreur 403 (Permissions) pour changer le nom du salon.")
                    return False
                else:
                    log.error(
                        f"Erreur HTTP ({e.status}) en changeant le nom du salon: {e}"
                    )
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
    ) -> bool | None:
        emoji_map = {
            Status.ONLINE: ONLINE_EMOJI,
            Status.OFFLINE: OFFLINE_EMOJI,
            Status.MAINTENANCE: MAINTENANCE_EMOJI,
        }
        log_embed = discord.Embed(
            title=f"{emoji_map.get(status)}・Bot {status.value}",
            description=f"Le bot est maintenant **{status.value}**.",
            color=COLOR_ONLINE
            if status == Status.ONLINE
            else COLOR_OFFLINE
            if status == Status.OFFLINE
            else COLOR_MAINTENANCE,
        )
        if manual:  # E701
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

    async def _send_ping(
        self, channel: discord.TextChannel, status: Status
    ) -> bool | None:
        if status == Status.MAINTENANCE:  # E701
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

    async def _update_status_logic(
        self,
        interaction: discord.Interaction | None = None,
        forced_status: Status | None = None,
        reason: str | None = None,
    ) -> None:
        async with self._update_lock:
            progress_log = []
            is_interactive = interaction is not None

            if is_interactive:
                status_msg = forced_status.value if forced_status else "auto"
                if reason:
                    status_msg += f" (Raison: {reason})"
                progress_log.append(
                    f"⏳ **Mise à jour vers `{status_msg}` en cours...**"
                )
                await interaction.edit_original_response(
                    content="\n".join(progress_log)
                )

            # 1. Déterminer le statut cible
            is_manual = forced_status is not None
            if is_manual:
                target_status = forced_status
            else:
                target_bot_member = next(
                    (
                        g.get_member(BOT_ID)
                        for g in self.bot.guilds
                        if g.get_member(BOT_ID)
                    ),
                    None,
                )
                if not target_bot_member:
                    log.warning(f"Bot cible (ID: {BOT_ID}) introuvable.")
                    return
                target_status = (
                    Status.ONLINE
                    if target_bot_member.status != discord.Status.offline
                    else Status.OFFLINE
                )

            # 2. Récupérer les indicateurs visuels
            channel = self.bot.get_channel(CHANNEL_ID)
            if not channel:  # E701
                return
            try:
                message = await channel.fetch_message(MESSAGE_ID)
                embed_status = self._get_status_from_embed(
                    message.embeds[0] if message.embeds else None
                )
            except (discord.NotFound, discord.Forbidden) as e:
                log.error(
                    f"Impossible de récupérer le message de statut (ID: {MESSAGE_ID}). Erreur: {e}"
                )
                if is_interactive:
                    # E701: Multiple statements on one line (colon)
                    await interaction.followup.send(
                        "❌ Message de statut introuvable.", ephemeral=True
                    )
                return

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
                if is_interactive:
                    # E701: Multiple statements on one line (colon)
                    await interaction.edit_original_response(
                        content="✅ Tout est déjà à jour."
                    )
                return

            # Actions de mise à jour
            if embed_is_inconsistent or is_manual:
                if await self._update_embed(message, target_status, reason=reason):
                    if is_interactive:
                        progress_log.append("✅ Message de statut mis à jour.")
                        await interaction.edit_original_response(
                            content="\n".join(progress_log)
                        )
                elif is_interactive:
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
                    if is_interactive:
                        progress_log.append("✅ Nom du salon mis à jour.")
                        await interaction.edit_original_response(
                            content="\n".join(progress_log)
                        )
                elif is_interactive:
                    progress_log.append("❌ Échec de la mise à jour du nom du salon.")
                    await interaction.edit_original_response(
                        content="\n".join(progress_log)
                    )

            # Actions de notification (uniquement si le statut change)
            if status_has_changed or (
                is_manual and target_status != self._last_known_status
            ):
                # SIM102: Use a single `if` statement
                if (
                    (logs_channel := self.bot.get_channel(LOGS_CHANNEL_ID))
                    and await self._send_log(
                        logs_channel, target_status, manual=is_manual, reason=reason
                    )
                    and is_interactive
                ):
                    progress_log.append("📄 Message de log envoyé.")
                    await interaction.edit_original_response(
                        content="\n".join(progress_log)
                    )

                if await self._send_ping(channel, target_status) and is_interactive:
                    progress_log.append("🔔 Notification envoyée.")
                    await interaction.edit_original_response(
                        content="\n".join(progress_log)
                    )

            self._last_known_status = target_status

            if is_interactive:
                progress_log.append("\n🎉 Opération terminée.")
                await interaction.edit_original_response(
                    content="\n".join(progress_log)
                )

    @_automatic_check_task.before_loop
    async def before_check(self) -> None:
        await self.bot.wait_until_ready()
        log.info("Initialisation du statut avant le démarrage de la boucle...")
        channel = self.bot.get_channel(CHANNEL_ID)
        if not channel:  # E701
            return
        try:
            message = await channel.fetch_message(MESSAGE_ID)
            self._last_known_status = self._get_status_from_embed(
                message.embeds[0] if message.embeds else None
            )
            if self._last_known_status:
                log.info(
                    f"Statut initialisé à partir du message existant : {self._last_known_status.name}"
                )
        except (discord.NotFound, discord.Forbidden):
            log.warning(
                f"Message de statut (ID: {MESSAGE_ID}) non trouvé/accessible pour l'initialisation."
            )

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
    @commands.is_owner()
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


async def setup(bot) -> None:
    await bot.add_cog(Statut(bot))
