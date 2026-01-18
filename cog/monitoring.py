import logging
import os

import aiohttp
from discord.ext import commands, tasks

log = logging.getLogger(__name__)


class Status(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.heartbeat_task.start()

    def cog_unload(self) -> None:
        self.heartbeat_task.cancel()

    @tasks.loop(seconds=60)
    async def heartbeat_task(self) -> None:
        # Deep Health Check : Si le bot est déconnecté ou fermé, on n'envoie rien.
        if self.bot.is_closed():
            return

        # Vérification de la latence (si > 500ms, on considère que le bot lag trop pour être "sain")
        # self.bot.latency est en secondes.
        if self.bot.latency > 0.5:
            log.warning(
                f"🔴 [Heartbeat] Latence élevée ({self.bot.latency * 1000:.0f}ms), heartbeat ignoré."
            )
            return

        # (Optionnel) Tu pourrais ajouter ici un check DB : await data_manager.check_connection()

        url = os.getenv("HEARTBEAT")
        if not url:
            log.warning(
                "⚠️ [Heartbeat] URL non trouvée dans les variables d'environnement (HEARTBEAT)."
            )
            return

        try:
            async with aiohttp.request("GET", url) as response:
                if response.status != 200:
                    log.error(f"🔴 [Heartbeat] Échec de l'envoi : {response.status}")
        except Exception as e:
            log.error(f"🔴 [Heartbeat] Erreur : {e}")

    @heartbeat_task.before_loop
    async def before_heartbeat(self) -> None:
        # On attend que le bot soit totalement prêt avant de commencer à pinger
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Status(bot))
