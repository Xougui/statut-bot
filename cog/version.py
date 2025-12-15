import json
import logging

import discord
from discord import app_commands
from discord.ext import commands

# Configurez le logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class Version(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="version", description="Change la version du bot dans le json."
    )
    @app_commands.describe(version="La version à définir pour le bot.")
    async def version(self, interaction: discord.Interaction, version: str) -> None:
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
