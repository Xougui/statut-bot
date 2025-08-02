import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import asyncio
import requests
import io
import PARAM
from dotenv import load_dotenv
import os
import logging

# Configurez le logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

# ID du canal où les mises à jour seront envoyées
UPDATE_CHANNEL_ID = 1345064533173080166 # ID corrigé
# Emoji à utiliser pour les éléments de la checklist
CHECKLIST_EMOJI = PARAM.checkmark
CROSSMARK_EMOJI = PARAM.crossmarck
IN_PROGRESS_EMOJI = PARAM.in_progress
ANNONCE_EMOJI = PARAM.annonce
TEST_EMOJI = PARAM.test

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
        # URL de l'API Gemini, stockée une fois pour être réutilisée
        self.api_url_gemini = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={self.gemini_api_key}"


    # Champ de texte pour le nom de la mise à jour
    update_name = ui.TextInput(
        label='Nom de la Mise à Jour (ex: v1.2.3)',
        placeholder='Entrez le nom ou la version de la mise à jour...',
        max_length=100,
        required=True
    )

    # Champ de texte pour un petit mot d'introduction facultatif
    intro_message = ui.TextInput(
        label='Message d\'introduction (facultatif)',
        placeholder='Ajoutez un petit mot au début de l\'annonce (ex: "Chers utilisateurs,").',
        max_length=500,
        required=False, # Rendu facultatif
        row=1 # Positionnement
    )

    # Champ de texte pour la description des changements
    changes = ui.TextInput(
        label='Qu\'est-ce qui a changé ?',
        style=discord.TextStyle.paragraph,
        # Placeholder raccourci pour respecter la limite de 100 caractères de Discord
        placeholder='Décrivez les changements, nouvelles fonctionnalités, corrections de bugs (sauts de ligne supportés).',
        max_length=2000,
        required=True,
        row=2 # Positionnement
    )

    # Champ de texte pour un petit mot de conclusion facultatif
    outro_message = ui.TextInput(
        label='Message de conclusion (facultatif)',
        placeholder='Ajoutez un petit mot à la fin de l\'annonce (ex: "Merci de votre soutien !").',
        max_length=500,
        required=False, # Rendu facultatif
        row=3 # Positionnement
    )

    async def _translate_text(self, title_fr_original: str, changes_fr_original: str,
                               intro_fr_original: str, outro_fr_original: str) -> tuple[str, str, str, str, str, str, str, str]:
        """
        Corrige l'orthographe française puis traduit le titre, les changements,
        le message d'introduction et de conclusion du français à l'anglais en utilisant l'API Gemini.
        Demande des réponses JSON structurées pour une meilleure robustesse.

        Args:
            title_fr_original (str): Le titre de la mise à jour en français (original).
            changes_fr_original (str): Les changements de la mise à jour en français (original).
            intro_fr_original (str): Le message d'introduction en français (original).
            outro_fr_original (str): Le message de conclusion en français (original).

        Returns:
            tuple[str, str, str, str, str, str, str, str]: Un tuple contenant:
                                     - Le titre corrigé en français
                                     - Les changements corrigés en français
                                     - Le message d'introduction corrigé en français
                                     - Le message de conclusion corrigé en français
                                     - Le titre traduit en anglais
                                     - Les changements traduits en anglais
                                     - Le message d'introduction traduit en anglais
                                     - Le message de conclusion traduit en anglais
                                     Retourne des chaînes vides pour les traductions/corrections si une étape échoue.
        """
        # --- Étape 1: Correction orthographique et grammaticale en français ---
        corrected_title_fr = title_fr_original
        corrected_changes_fr = changes_fr_original
        corrected_intro_fr = intro_fr_original
        corrected_outro_fr = outro_fr_original

        prompt_correction = f"Corrigez les fautes d'orthographe et de grammaire dans le texte français suivant. Répondez uniquement avec un objet JSON. L'objet JSON doit avoir quatre clés: 'corrected_title', 'corrected_changes', 'corrected_intro', et 'corrected_outro'. Les valeurs de ces clés doivent être le texte corrigé, sans préfixes. Assurez-vous de préserver tous les sauts de ligne originaux (`\\n`) dans le texte corrigé des changements.\n\n" \
                            f"Titre: {title_fr_original}\n" \
                            f"Changements: {changes_fr_original}\n" \
                            f"Introduction: {intro_fr_original}\n" \
                            f"Conclusion: {outro_fr_original}"

        chatHistory_correction = [{ "role": "user", "parts": [{ "text": prompt_correction }] }]
        payload_correction = {
            "contents": chatHistory_correction,
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "corrected_title": { "type": "STRING" },
                        "corrected_changes": { "type": "STRING" },
                        "corrected_intro": { "type": "STRING" },
                        "corrected_outro": { "type": "STRING" }
                    },
                    "propertyOrdering": ["corrected_title", "corrected_changes", "corrected_intro", "corrected_outro"]
                }
            }
        }

        retries_correction = 0
        max_retries_correction = 3 # Nombre de tentatives pour la correction française
        while retries_correction < max_retries_correction:
            try:
                response_correction = await asyncio.to_thread(
                    lambda: requests.post(self.api_url_gemini, headers={'Content-Type': 'application/json'}, data=json.dumps(payload_correction))
                )
                response_correction.raise_for_status()
                result_correction = response_correction.json()

                if result_correction.get("candidates") and result_correction["candidates"][0].get("content") and result_correction["candidates"][0]["content"].get("parts"):
                    json_str_correction = result_correction["candidates"][0]["content"]["parts"][0]["text"]
                    corrected_data = json.loads(json_str_correction)
                    corrected_title_fr = corrected_data.get("corrected_title", title_fr_original) # Fallback au texte original si correction échoue
                    corrected_changes_fr = corrected_data.get("corrected_changes", changes_fr_original) # Fallback au texte original
                    corrected_intro_fr = corrected_data.get("corrected_intro", intro_fr_original)
                    corrected_outro_fr = corrected_data.get("corrected_outro", outro_fr_original)
                    corrected_changes_fr = corrected_changes_fr.replace('\\n', '\n') # Assurer la préservation des sauts de ligne
                    logging.info("Correction française réussie.")
                    break # Correction réussie, sortir de la boucle de réessai
                else:
                    logging.warning("Erreur: La structure de la réponse de l'API Gemini pour la correction est inattendue. Utilisation du texte original.")
                    break # Pas de réponse valide, ne pas réessayer
            except requests.exceptions.RequestException as e:
                logging.error(f"Erreur lors de l'appel à l'API Gemini pour la correction (tentative {retries_correction + 1}/{max_retries_correction}): {e}")
                retries_correction += 1
                await asyncio.sleep(2 ** retries_correction) # Backoff exponentiel
            except json.JSONDecodeError as e:
                logging.error(f"Erreur de décodage JSON de la réponse Gemini pour la correction: {e}. Utilisation du texte original.")
                break # Erreur de décodage JSON, pas de raison de réessayer
            except Exception as e:
                logging.error(f"Une erreur inattendue est survenue lors de la correction française: {e}. Utilisation du texte original.", exc_info=True)
                break # Autre erreur inattendue, pas de raison de réessayer
        else: # Ce bloc 'else' s'exécute si la boucle se termine sans 'break' (toutes les tentatives ont échoué)
            logging.error(f"Échec de la correction française après {max_retries_correction} tentatives. Utilisation du texte original.")

        # --- Étape 2: Traduction du français corrigé vers l'anglais ---
        translated_title = ""
        translated_changes = ""
        translated_intro = ""
        translated_outro = ""

        prompt_translation = f"Traduisez le texte suivant du français à l'anglais. Répondez uniquement avec un objet JSON. L'objet JSON doit avoir quatre clés: 'title', 'changes', 'intro', et 'outro'. Les valeurs de ces clés doivent être la traduction pure, sans préfixes comme 'Titre:' ou 'Changes:'. Assurez-vous de préserver tous les sauts de ligne originaux (`\\n`) dans la traduction des changements. Corrigez les fautes d'orthographe.\n\n" \
                             f"Titre original: {corrected_title_fr}\n" \
                             f"Changements originaux: {corrected_changes_fr}\n" \
                             f"Introduction originale: {corrected_intro_fr}\n" \
                             f"Conclusion originale: {corrected_outro_fr}"

        chatHistory_translation = [{ "role": "user", "parts": [{ "text": prompt_translation }] }]
        payload_translation = {
            "contents": chatHistory_translation,
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "title": { "type": "STRING" },
                        "changes": { "type": "STRING" },
                        "intro": { "type": "STRING" },
                        "outro": { "type": "STRING" }
                    },
                    "propertyOrdering": ["title", "changes", "intro", "outro"]
                }
            }
        }

        retries_translation = 0
        max_retries_translation = 5 # Nombre de tentatives pour la traduction
        while retries_translation < max_retries_translation:
            try:
                response_translation = await asyncio.to_thread(
                    lambda: requests.post(self.api_url_gemini, headers={'Content-Type': 'application/json'}, data=json.dumps(payload_translation))
                )
                response_translation.raise_for_status()
                result_translation = response_translation.json()

                if result_translation.get("candidates") and result_translation["candidates"][0].get("content") and result_translation["candidates"][0]["content"].get("parts"):
                    json_str_translation = result_translation["candidates"][0]["content"]["parts"][0]["text"]
                    translated_data = json.loads(json_str_translation)

                    translated_title = translated_data.get("title", "")
                    translated_changes = translated_data.get("changes", "")
                    translated_intro = translated_data.get("intro", "")
                    translated_outro = translated_data.get("outro", "")

                    # Nettoyage supplémentaire pour s'assurer qu'il n'y a pas de préfixes indésirables
                    translated_title = translated_title.replace("Title: ", "").replace("Titre: ", "").strip()
                    translated_changes = translated_changes.replace("Changes: ", "").replace("Changements: ", "").strip()
                    translated_intro = translated_intro.replace("Introduction: ", "").replace("Introduction originale: ", "").strip()
                    translated_outro = translated_outro.replace("Conclusion: ", "").replace("Conclusion originale: ", "").strip()

                    translated_changes = translated_changes.replace('\\n', '\n') # Remplacer les doubles backslashes par un vrai saut de ligne
                    translated_changes = translated_changes.replace('&', CHECKLIST_EMOJI).replace('~', CROSSMARK_EMOJI).replace('{', f"{IN_PROGRESS_EMOJI}") # Appliquer les emojis de checklist et de croix

                    logging.info("Traduction anglaise réussie.")
                    break # Traduction réussie, sortir de la boucle de réessai
                else:
                    logging.warning("Erreur: La structure de la réponse de l'API Gemini pour la traduction est inattendue.")
                    break # Pas de réponse valide, ne pas réessayer
            except requests.exceptions.RequestException as e:
                logging.error(f"Erreur lors de l'appel à l'API Gemini pour la traduction (tentative {retries_translation + 1}/{max_retries_translation}): {e}")
                retries_translation += 1
                await asyncio.sleep(2 ** retries_translation)
            except json.JSONDecodeError as e:
                logging.error(f"Erreur de décodage JSON de la réponse Gemini pour la traduction: {e}")
                break
            except Exception as e:
                logging.error(f"Une erreur inattendue est survenue lors de la traduction: {e}", exc_info=True)
                break
        else:
            logging.error(f"Échec de la traduction après {max_retries_translation} tentatives.")

        # Retourne le titre et les changements corrigés en français, et les traductions en anglais
        return (corrected_title_fr, corrected_changes_fr, corrected_intro_fr, corrected_outro_fr,
                translated_title, translated_changes, translated_intro, translated_outro)

    async def on_submit(self, interaction: discord.Interaction):
        """
        Gère la soumission du modal. Récupère les données, tente la correction et la traduction,
        et envoie le message de mise à jour au canal Discord.
        """
        await interaction.response.defer(thinking=True, ephemeral=True)

        # Les valeurs originales du modal
        original_title_fr = self.update_name.value
        original_changes_fr = self.changes.value
        original_intro_fr = self.intro_message.value if self.intro_message.value else ""
        original_outro_fr = self.outro_message.value if self.outro_message.value else ""


        # Tente de corriger le français puis de traduire
        (corrected_title_fr, corrected_changes_fr, corrected_intro_fr, corrected_outro_fr,
         translated_title, translated_changes, translated_intro, translated_outro) = await self._translate_text(
            original_title_fr, original_changes_fr, original_intro_fr, original_outro_fr
        )

        # Appliquer l'emoji de checklist au texte français CORRIGÉ
        final_changes_fr_display = corrected_changes_fr.replace('&', f"{CHECKLIST_EMOJI}:").replace('~', f"{CROSSMARK_EMOJI}:").replace('{', f"{IN_PROGRESS_EMOJI}:")

        # Construction du message français
        french_message_parts = [
            f"# {ANNONCE_EMOJI} {corrected_title_fr} {ANNONCE_EMOJI}\n\n", # Titre de la maj
            f"👋 Coucou à toute la communauté !\n\n" # Coucou à la commu
        ]
        if corrected_intro_fr:
            french_message_parts.append(f"{corrected_intro_fr}\n\n") # Mot d'intro
        
        french_message_parts.append(
            f"{TEST_EMOJI} <@1335228717403996160> a reçu une mise à jour !\n\n" # Mention utilisateur et maj
            f"Voici les changements et améliorations que nous avons apportés :\n"
            f"{final_changes_fr_display}\n\n" # Changements
        )
        if corrected_outro_fr:
            french_message_parts.append(f"{corrected_outro_fr}\n\n") # Mot conclusion
        
        french_message_parts.append(
            f"🚀 Restez connectés pour de futures annonces et merci pour votre soutien continu ! **Utilisez /feedback pour signaler des erreurs ou des bugs ou allez dans <#1350399062418915418>.**\n"
            f"L'équipe de développement." # Conclusion
        )
        french_message_content = "".join(french_message_parts)

        # Construction du message anglais
        english_message_content = ""
        if translated_title and translated_changes:
            english_message_parts = [
                f"# {ANNONCE_EMOJI} {translated_title} {ANNONCE_EMOJI}\n\n", # Update Title
                f"👋 Hello to the entire community!\n\n" # Hello to the community
            ]
            if translated_intro:
                english_message_parts.append(f"{translated_intro}\n\n") # Intro message
            
            # Translate the specific user update message
            translated_user_update = "received an update !"
            english_message_parts.append(
                f"{TEST_EMOJI} <@1335228717403996160> {translated_user_update}\n\n" # User mention and update
                f"Here are the changes and improvements we've made:\n"
                f"{translated_changes}\n\n" # Changes
            )
            if translated_outro:
                english_message_parts.append(f"{translated_outro}\n\n") # Outro message
            
            english_message_parts.append(
                f"🚀 Stay tuned for future announcements and thank you for your continued support! **Use /feedback to report errors or bugs or go to <#1350399062418915418>.**\n"
                f"The Development Team." # Conclusion
            )
            english_message_content = "".join(english_message_parts)
        else:
            # Message de fallback si la traduction échoue
            english_message_content = f"### {CROSSMARK_EMOJI} Translation failed\n\n"
            await interaction.followup.send(
                "Avertissement : La traduction automatique de la mise à jour a échoué. "
                "Le message sera envoyé sans traduction.",
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
            combined_message_content = f"<@&1350428823052746752>\n\n{french_message_content}\n\n---\n\n{english_message_content}\n\n---\n\n-# [Support server](<{PARAM.support_server}>) "

            msg = await target_channel.send(content=combined_message_content, files=files_to_send)

            # Si le canal est un canal d'annonces, le message est publié
            if isinstance(target_channel, discord.TextChannel) and target_channel.is_news():
                try:
                    await msg.publish()
                    logging.info(f"Message publié dans le canal d'annonces {target_channel.name} ({target_channel.id}).")
                except discord.Forbidden:
                    logging.error(f"Permissions insuffisantes pour publier le message dans le canal d'annonces {target_channel.name} ({target_channel.id}).")
                    await interaction.followup.send(
                        "Je n'ai pas la permission de publier le message dans ce canal d'annonces. "
                        "Veuillez vérifier mes permissions (Gérer les messages).", ephemeral=True
                    )
                except Exception as e:
                    logging.error(f"Une erreur inattendue est survenue lors de la publication du message : {e}", exc_info=True)
                    await interaction.followup.send(f"Une erreur est survenue lors de la publication du message : {e}", ephemeral=True)

            await interaction.followup.send("L'annonce de mise à jour a été envoyée avec succès !", ephemeral=True)
        except discord.Forbidden:
            logging.error(f"Permissions insuffisantes pour envoyer/publier dans le canal {self.update_channel_id}.")
            await interaction.followup.send(
                "Je n'ai pas la permission d'envoyer des messages dans ce canal. "
                "Veuillez vérifier mes permissions.", ephemeral=True
            )
        except Exception as e:
            logging.error(f"Une erreur est survenue lors de l'envoi du message : {e}", exc_info=True)
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
        if interaction.response.is_done():
            # Si l'interaction a déjà été répondue (ex: modal envoyé, mais erreur dans on_submit)
            # Utiliser followup.send
            try:
                if isinstance(error, app_commands.CheckFailure):
                    # L'erreur est déjà gérée par is_owner()
                    pass
                elif isinstance(error, app_commands.CommandOnCooldown):
                    await interaction.followup.send(
                        f"Cette commande est en cooldown. Veuillez réessayer dans {error.retry_after:.1f} secondes.",
                        ephemeral=True
                    )
                else:
                    logging.error(f"Erreur inattendue dans /update (followup): {error}", exc_info=True)
                    await interaction.followup.send(
                        f"Une erreur est survenue lors de l'exécution de la commande : {error}",
                        ephemeral=True
                    )
            except discord.errors.NotFound:
                logging.error(f"Erreur: Interaction déjà perdue lors de la gestion d'erreur (tentative de followup): {error}")
        else:
            # Si l'interaction n'a PAS encore été répondue (ex: erreur avant l'envoi du modal, ou send_modal a échoué)
            # Utiliser la réponse initiale
            try:
                if isinstance(error, app_commands.CheckFailure):
                    await interaction.response.send_message("Vous n'êtes pas autorisé à utiliser cette commande.", ephemeral=True)
                elif isinstance(error, app_commands.CommandOnCooldown):
                    await interaction.response.send_message(
                        f"Cette commande est en cooldown. Veuillez réessayer dans {error.retry_after:.1f} secondes.",
                        ephemeral=True
                    )
                else:
                    logging.error(f"Erreur inattendue dans /update (réponse initiale): {error}", exc_info=True)
                    await interaction.response.send_message(
                        f"Une erreur est survenue lors de l'exécution de la commande : {error}",
                        ephemeral=True
                    )
            except discord.errors.NotFound:
                logging.error(f"Erreur: Interaction déjà perdue lors de la gestion d'erreur (tentative de réponse initiale): {error}")


async def setup(bot: commands.Bot):
    """
    Fonction de configuration pour ajouter le Cog au bot.
    """
    await bot.add_cog(ManagementCog(bot))
