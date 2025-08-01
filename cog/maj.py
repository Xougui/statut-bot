import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import asyncio
import requests
import io
from dotenv import load_dotenv
import os
import logging

# Configurez le logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

# ID du canal où les mises à jour seront envoyées
UPDATE_CHANNEL_ID = 1388563226005864573
# Emoji à utiliser pour les éléments de la checklist
CHECKLIST_EMOJI = "✅"

# Importation des paramètres (assurez-vous que PARAM.py existe et est sécurisé)
import PARAM

# Récupération de la clé API Gemini depuis les variables d'environnement
gemini_api_key = os.getenv("GEMINI_API")

class UpdateModal(ui.Modal, title='Nouvelle Mise à Jour'):
    """
    Modal Discord pour collecter les informations d'une nouvelle mise à jour.
    Permet à l'utilisateur de saisir le nom de la mise à jour et les changements.
    """
    def __init__(self, attachments: list[discord.Attachment]):
        super().__init__()
        self.attachments = attachments
        self.update_channel_id = UPDATE_CHANNEL_ID
        self.gemini_api_key = gemini_api_key # Stocker la clé API pour utilisation dans les méthodes

    # Champ de texte pour le nom de la mise à jour
    update_name = ui.TextInput(
        label='Nom de la Mise à Jour (ex: v1.2.3)',
        placeholder='Entrez le nom ou la version de la mise à jour...',
        max_length=100,
        required=True
    )

    # Champ de texte pour la description des changements
    changes = ui.TextInput(
        label='Qu\'est-ce qui a changé ?',
        style=discord.TextStyle.paragraph,
        placeholder='Décrivez les changements, les nouvelles fonctionnalités, les corrections de bugs...',
        max_length=2000,
        required=True
    )

    async def _translate_text(self, title_fr: str, changes_fr: str) -> tuple[str, str]:
        """
        Traduit le titre et les changements du français à l'anglais en utilisant l'API Gemini.
        Demande une réponse JSON structurée pour une meilleure robustesse.

        Args:
            title_fr (str): Le titre de la mise à jour en français.
            changes_fr (str): Les changements de la mise à jour en français.

        Returns:
            tuple[str, str]: Un tuple contenant le titre traduit et les changements traduits.
                             Retourne les chaînes vides si la traduction échoue.
        """
        prompt = f"Traduisez le texte suivant du français à l'anglais. Ne répondez qu'avec la traduction au format JSON. Corrigez les fautes d'orthographe. Le JSON doit avoir deux clés: 'title' et 'changes'.\n\n" \
                 f"Titre: {title_fr}\n" \
                 f"Changements: {changes_fr}"

        chatHistory = []
        chatHistory.append({ "role": "user", "parts": [{ "text": prompt }] })

        # Définition du schéma de réponse attendu pour Gemini
        payload = {
            "contents": chatHistory,
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "title": { "type": "STRING" },
                        "changes": { "type": "STRING" }
                    },
                    "propertyOrdering": ["title", "changes"]
                }
            }
        }
        apiUrl = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={self.gemini_api_key}"

        retries = 0
        max_retries = 5
        while retries < max_retries:
            try:
                response = await asyncio.to_thread(
                    lambda: requests.post(apiUrl, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
                )
                response.raise_for_status() # Lève une exception pour les codes d'état HTTP d'erreur

                result = response.json()
                if result.get("candidates") and result["candidates"][0].get("content") and result["candidates"][0]["content"].get("parts"):
                    # Le texte retourné par Gemini est déjà un JSON stringifié
                    json_str = result["candidates"][0]["content"]["parts"][0]["text"]
                    translated_data = json.loads(json_str)

                    translated_title = translated_data.get("title", "")
                    translated_changes = translated_data.get("changes", "").replace('&', CHECKLIST_EMOJI)
                    return translated_title, translated_changes
                else:
                    logging.warning("Erreur: La structure de la réponse de l'API Gemini est inattendue.")
                    return "", "" # Retourne des chaînes vides en cas d'échec de parsing
            except requests.exceptions.RequestException as e:
                logging.error(f"Erreur lors de l'appel à l'API Gemini (tentative {retries + 1}/{max_retries}): {e}")
                retries += 1
                await asyncio.sleep(2 ** retries) # Backoff exponentiel
            except json.JSONDecodeError as e:
                logging.error(f"Erreur de décodage JSON de la réponse Gemini: {e}")
                return "", "" # Retourne des chaînes vides en cas d'erreur JSON
            except Exception as e:
                logging.error(f"Une erreur inattendue est survenue lors de la traduction: {e}")
                return "", "" # Retourne des chaînes vides pour toute autre erreur

        logging.error(f"Échec de la traduction après {max_retries} tentatives.")
        return "", "" # Retourne des chaînes vides si toutes les tentatives échouent

    async def on_submit(self, interaction: discord.Interaction):
        """
        Gère la soumission du modal. Récupère les données, tente la traduction,
        et envoie le message de mise à jour au canal Discord.
        """
        # Déferrer la réponse pour avoir plus de temps, mais l'éphémère est géré par le modal lui-même.
        # Le modal est déjà "répondu" par l'affichage, donc nous utilisons followup pour les messages suivants.
        await interaction.response.defer(thinking=True, ephemeral=True)

        update_title_fr = self.update_name.value
        changes_fr = self.changes.value.replace('&', CHECKLIST_EMOJI)

        # Tente de traduire le titre et les changements
        translated_title, translated_changes = await self._translate_text(
            self.update_name.value, self.changes.value
        )

        french_message_content = f"📣 **GROSSE ANNONCE !** 📣\n\n" \
                                 f"Salut tout le monde !\n\n" \
                                 f"Nous avons une nouvelle mise à jour : **{update_title_fr}**\n\n" \
                                 f"Voici ce qui a changé :\n{changes_fr}\n\n" \
                                 f"Restez connectés pour les prochaines nouveautés !"

        english_message_content = ""
        if translated_title and translated_changes:
            english_message_content = f"📣 **BIG ANNOUNCEMENT!** 📣\n\n" \
                                      f"Hello everyone!\n\n" \
                                      f"We have a new update: **{translated_title}**\n\n" \
                                      f"Here's what changed:\n{translated_changes}\n\n" \
                                      f"Stay tuned for future updates!"
        else:
            # Message de fallback si la traduction échoue
            english_message_content = f"📣 **BIG ANNOUNCEMENT!** 📣\n\n" \
                                      f"Hello everyone!\n\n" \
                                      f"We have a new update: **{update_title_fr}**\n\n" \
                                      f"Here's what changed:\n(Translation failed. Original French content provided below)\n{self.changes.value.replace('&', CHECKLIST_EMOJI)}\n\n" \
                                      f"Stay tuned for future updates!"
            await interaction.followup.send(
                "Avertissement : La traduction automatique de la mise à jour a échoué. "
                "Le message sera envoyé avec le contenu original en français pour les changements en anglais.",
                ephemeral=True
            )


        target_channel = interaction.guild.get_channel(self.update_channel_id)
        if not target_channel:
            logging.error(f"Le canal avec l'ID {self.update_channel_id} n'a pas été trouvé.")
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
                logging.error(f"Impossible de télécharger la pièce jointe {attachment.filename}: {e}")
                await interaction.followup.send(f"Avertissement: Impossible d'attacher le fichier `{attachment.filename}`.", ephemeral=True)

        try:
            # Combinaison des messages français et anglais
            combined_message_content = f"{french_message_content}\n\n---\n\n{english_message_content}"

            msg = await target_channel.send(content=combined_message_content, files=files_to_send)

            # Si le canal est un canal d'annonces, le message est publié
            if isinstance(target_channel, discord.TextChannel) and target_channel.is_news():
                await msg.publish()

            await interaction.followup.send("L'annonce de mise à jour a été envoyée avec succès !", ephemeral=True)
        except discord.Forbidden:
            logging.error(f"Permissions insuffisantes pour envoyer/publier dans le canal {self.update_channel_id}.")
            await interaction.followup.send(
                "Je n'ai pas la permission d'envoyer des messages ou de les publier dans ce canal. "
                "Veuillez vérifier mes permissions.", ephemeral=True
            )
        except Exception as e:
            logging.error(f"Une erreur est survenue lors de l'envoi du message : {e}")
            await interaction.followup.send(f"Une erreur est survenue lors de l'envoi du message : {e}", ephemeral=True)


class ManagementCog(commands.Cog):
    """
    Cog Discord pour les commandes de gestion du bot.
    Contient la commande /update.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def is_owner():
        """
        Vérifie si l'utilisateur qui exécute la commande est un propriétaire défini dans PARAM.owners.
        """
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
    @is_owner() # Applique la vérification des propriétaires
    async def update_command(self, interaction: discord.Interaction, attachments: discord.Attachment = None):
        """
        Commande slash /update pour déclencher le modal de mise à jour.
        """
        files_for_modal = []
        if attachments:
            files_for_modal.append(attachments)

        modal = UpdateModal(attachments=files_for_modal)
        # Appelez send_modal directement sur interaction.response
        await interaction.response.send_modal(modal)

    @update_command.error
    async def update_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """
        Gestionnaire d'erreurs pour la commande /update.
        """
        if not interaction.response.is_done():
            try:
                await interaction.response.defer(ephemeral=True)
            except discord.errors.NotFound:
                logging.error(f"Erreur: Interaction déjà perdue lors de la gestion d'erreur: {error}")
                return

        if isinstance(error, app_commands.CheckFailure):
            # L'erreur est déjà gérée par is_owner() qui envoie un message éphémère
            pass
        elif isinstance(error, app_commands.CommandOnCooldown):
            await interaction.followup.send(
                f"Cette commande est en cooldown. Veuillez réessayer dans {error.retry_after:.1f} secondes.",
                ephemeral=True
            )
        else:
            logging.error(f"Erreur inattendue dans /update: {error}", exc_info=True) # exc_info=True pour le traceback
            await interaction.followup.send(
                f"Une erreur inattendue est survenue lors de l'exécution de la commande : {error}",
                ephemeral=True
            )


async def setup(bot: commands.Bot):
    """
    Fonction de configuration pour ajouter le Cog au bot.
    """
    await bot.add_cog(ManagementCog(bot))
    logging.info("ManagementCog chargé.") # Utilisation de logging ici aussi
