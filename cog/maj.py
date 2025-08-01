import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import asyncio
import requests
import io
from dotenv import load_dotenv
import os

load_dotenv()

UPDATE_CHANNEL_ID = 1388563226005864573
CHECKLIST_EMOJI = "✅"

import PARAM

gemini_api_key = os.getenv("GEMINI_API")

class UpdateModal(ui.Modal, title='Nouvelle Mise à Jour'):
    def __init__(self, attachments: list[discord.Attachment]):
        super().__init__()
        self.attachments = attachments
        self.update_channel_id = UPDATE_CHANNEL_ID

    update_name = ui.TextInput(
        label='Nom de la Mise à Jour (ex: v1.2.3)',
        placeholder='Entrez le nom ou la version de la mise à jour...',
        max_length=100,
        required=True
    )

    changes = ui.TextInput(
        label='Qu\'est-ce qui a changé ?',
        style=discord.TextStyle.paragraph,
        placeholder='Décrivez les changements, les nouvelles fonctionnalités, les corrections de bugs...',
        max_length=2000,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True, ephemeral=True) # Rendre le defer éphémère

        update_title_fr = self.update_name.value
        changes_fr = self.changes.value.replace('&', CHECKLIST_EMOJI)

        french_message_content = f"📣 **GROSSE ANNONCE !** 📣\n\n" \
                                 f"Salut tout le monde !\n\n" \
                                 f"Nous avons une nouvelle mise à jour : **{update_title_fr}**\n\n" \
                                 f"Voici ce qui a changé :\n{changes_fr}\n\n" \
                                 f"Restez connectés pour les prochaines nouveautés !"

        english_message_content = ""
        try:
            prompt = f"Traduisez le texte suivant du français à l'anglais. Ne répondez qu'avec la traduction.\n\n" \
                     f"Titre: {update_title_fr}\n" \
                     f"Changements: {self.changes.value}"

            chatHistory = []
            chatHistory.append({ "role": "user", "parts": [{ "text": prompt }] })
            payload = { "contents": chatHistory }
            apiUrl = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={gemini_api_key}"

            retries = 0
            max_retries = 5
            while retries < max_retries:
                try:
                    response = await asyncio.to_thread(
                        lambda: requests.post(apiUrl, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
                    )
                    response.raise_for_status()
                    result = response.json()

                    if result.get("candidates") and result["candidates"][0].get("content") and result["candidates"][0]["content"].get("parts"):
                        translated_text = result["candidates"][0]["content"]["parts"][0]["text"]
                        lines = translated_text.split('\n')
                        translated_title = ""
                        translated_changes = ""
                        for line in lines:
                            if line.startswith("Title:"):
                                translated_title = line.replace("Title:", "").strip()
                            elif line.startswith("Changes:"):
                                translated_changes = line.replace("Changes:", "").strip().replace('&', CHECKLIST_EMOJI)

                        if translated_title and translated_changes:
                            english_message_content = f"📣 **BIG ANNOUNCEMENT!** 📣\n\n" \
                                                      f"Hello everyone!\n\n" \
                                                      f"We have a new update: **{translated_title}**\n\n" \
                                                      f"Here's what changed:\n{translated_changes}\n\n" \
                                                      f"Stay tuned for future updates!"
                        else:
                            english_message_content = f"📣 **BIG ANNOUNCEMENT!** 📣\n\n" \
                                                      f"Hello everyone!\n\n" \
                                                      f"We have a new update: **{update_title_fr}**\n\n" \
                                                      f"Here's what changed:\n{translated_text.replace('&', CHECKLIST_EMOJI)}\n\n" \
                                                      f"Stay tuned for future updates!"
                        break
                    else:
                        print("Erreur: La structure de la réponse de l'API Gemini est inattendue.")
                        english_message_content = f"Could not translate. Original changes:\n{self.changes.value.replace('&', CHECKLIST_EMOJI)}"
                        break
                except requests.exceptions.RequestException as e:
                    print(f"Erreur lors de l'appel à l'API Gemini (tentative {retries + 1}/{max_retries}): {e}")
                    retries += 1
                    await asyncio.sleep(2 ** retries)
                except json.JSONDecodeError as e:
                    print(f"Erreur de décodage JSON de la réponse Gemini: {e}")
                    english_message_content = f"Could not translate due to API response error. Original changes:\n{self.changes.value.replace('&', CHECKLIST_EMOJI)}"
                    break
        except Exception as e:
            print(f"Une erreur inattendue est survenue lors de la traduction: {e}")
            english_message_content = f"Could not translate due to an unexpected error. Original changes:\n{self.changes.value.replace('&', CHECKLIST_EMOJI)}"

        target_channel = interaction.guild.get_channel(self.update_channel_id)
        if not target_channel:
            await interaction.followup.send(
                f"Erreur: Le canal avec l'ID `{self.update_channel_id}` n'a pas été trouvé. "
                "Veuillez vérifier l'ID configuré.", ephemeral=True
            )
            return

        files_to_send = []
        for attachment in self.attachments:
            try:
                file_bytes = await attachment.read()
                files_to_send.append(discord.File(fp=io.BytesIO(file_bytes), filename=attachment.filename))
            except Exception as e:
                print(f"Impossible de télécharger la pièce jointe {attachment.filename}: {e}")
                await interaction.followup.send(f"Avertissement: Impossible d'attacher le fichier `{attachment.filename}`.", ephemeral=True)

        try:
            # Combinaison des messages français et anglais
            combined_message_content = f"{french_message_content}\n\n---\n\n{english_message_content}"

            msg = await target_channel.send(content=combined_message_content, files=files_to_send)

            if isinstance(target_channel, discord.TextChannel) and target_channel.is_news():
                await msg.publish()

            await interaction.followup.send("L'annonce de mise à jour a été envoyée avec succès !", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "Je n'ai pas la permission d'envoyer des messages ou de les publier dans ce canal. "
                "Veuillez vérifier mes permissions.", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"Une erreur est survenue lors de l'envoi du message : {e}", ephemeral=True)


class ManagementCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def is_owner():
        async def predicate(interaction: discord.Interaction):
            if interaction.user.id not in PARAM.owners:
                await interaction.response.send_message("Vous n'êtes pas autorisé à utiliser cette commande.", ephemeral=True)
                return False
            return True
        return app_commands.check(predicate)

    @app_commands.command(name="update", description="[🤖 Dev ] Envoie une annonce de mise à jour du bot.")
    @app_commands.describe(
        attachments="Fichier à joindre à l'annonce (image, document, etc.)"
    )
    @is_owner()
    async def update_command(self, interaction: discord.Interaction, attachments: discord.Attachment = None):
        files_for_modal = []
        if attachments:
            files_for_modal.append(attachments)

        modal = UpdateModal(attachments=files_for_modal)
        await interaction.response.send_modal(modal)

    @update_command.error
    async def update_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if not interaction.response.is_done():
            try:
                await interaction.response.defer(ephemeral=True)
            except discord.errors.NotFound:
                print(f"Erreur: Interaction déjà perdue lors de la gestion d'erreur: {error}")
                return

        if isinstance(error, app_commands.CheckFailure):
            pass
        elif isinstance(error, app_commands.CommandOnCooldown):
            await interaction.followup.send(
                f"Cette commande est en cooldown. Veuillez réessayer dans {error.retry_after:.1f} secondes.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"Une erreur inattendue est survenue lors de l'exécution de la commande : {error}",
                ephemeral=True
            )
            print(f"Erreur inattendue dans /update: {error}")

async def setup(bot: commands.Bot):
    await bot.add_cog(ManagementCog(bot))
    print("ManagementCog chargé.")
