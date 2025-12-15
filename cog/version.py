from collections.abc import Callable
import json
import logging
import re

import discord
from discord import app_commands
from discord.ext import commands

import PARAM

# Configurez le logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


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


class Version(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="version", description="Change la version du bot dans le json."
    )
    @app_commands.describe(version="La version à définir pour le bot.")
    @is_owner()
    async def version(self, interaction: discord.Interaction, version: str) -> None:
        if not re.match(r"^\d+\.\d+\.\d+$", version):
            await interaction.response.send_message(
                "❌ Format invalide. La version doit être sous la forme `x.y.z` (ex: 1.0.0).",
                ephemeral=True,
            )
            return

        try:
            with open("version.json", "w") as f:
                json.dump({"version": version}, f, indent=2)
            logging.info(f"Version mise à jour vers : {version}")
            await interaction.response.send_message(
                f"Version mise à jour vers : {version}", ephemeral=True
            )
        except OSError as e:
            logging.error(f"Impossible de sauvegarder la version : {e}")
            await interaction.response.send_message(
                "Impossible de sauvegarder la version.", ephemeral=True
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Version(bot))
