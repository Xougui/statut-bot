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

# ID des canaux où les mises à jour seront envoyées
UPDATE_CHANNEL_ID_FR = 1345064533173080166  # Salon français
UPDATE_CHANNEL_ID_EN = 1421773639761526824  # Salon anglais
UPDATE_CHANNEL_ID_TEST = 1350138595515568169 # Salon de test

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
    def __init__(self, attachments: list[discord.Attachment], is_test_run: bool):
        super().__init__()
        self.attachments = attachments
        self.is_test_run = is_test_run
        self.gemini_api_key = gemini_api_key
        self.api_url_gemini = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={self.gemini_api_key}"

        # Charger la version actuelle et la pré-remplir dans le champ de version
        try:
            with open('version.json', 'r') as f:
                data = json.load(f)
                current_version = data.get('version', '1.0.0')
        except (FileNotFoundError, json.JSONDecodeError):
            current_version = '1.0.0'  # Version par défaut si le fichier n'existe pas ou est corrompu
        self.version_number.default = current_version

    # Champ de texte pour le nom de la mise à jour
    update_name = ui.TextInput(
        label='Nom de la Mise à Jour (ex: v1.2.3)',
        placeholder='Entrez le nom ou la version de la mise à jour...',
        max_length=100,
        required=True
    )

    # Champ pour le numéro de version
    version_number = ui.TextInput(
        label='Numéro de version (ex: 1.0.1)',
        placeholder='Sera sauvegardé pour /patch-note',
        max_length=20,
        required=True
    )

    # Champ de texte pour un petit mot d'introduction facultatif
    intro_message = ui.TextInput(
        label='Message d\'introduction (facultatif)',
        placeholder='Ajoutez un petit mot au début de l\'annonce (ex: "Chers utilisateurs,").',
        max_length=500,
        required=False
    )

    # Champ de texte pour la description des changements
    changes = ui.TextInput(
        label='Qu\'est-ce qui a changé ? &:✅ / ~:❌ / £:⏳',
        style=discord.TextStyle.paragraph,
        placeholder='Décrivez les changements, nouvelles fonctionnalités, corrections de bugs (sauts de ligne supportés).',
        max_length=2000,
        required=True
    )

    # Champ de texte pour un petit mot de conclusion facultatif
    outro_message = ui.TextInput(
        label='Message de conclusion (facultatif)',
        placeholder='Ajoutez un petit mot à la fin de l\'annonce (ex: "Merci de votre soutien !").',
        max_length=500,
        required=False
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

        prompt_correction = f"Corrigez les fautes d'orthographe et de grammaire dans le texte français suivant. Répondez uniquement avec un objet JSON. L'objet JSON doit avoir quatre clés: 'corrected_title', 'corrected_changes', 'corrected_intro', et 'corrected_outro'. Les valeurs de ces clés doivent être le texte corrigé, sans préfixes. Assurez-vous de préserver tous les sauts de ligne originaux (`\\n`) dans le texte corrigé des changements. N'enlève pas les caractères spéciaux comme &; ~; £.\n\n" \
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

        prompt_translation = f"Traduisez le texte suivant du français à l'anglais. Répondez uniquement avec un objet JSON. L'objet JSON doit avoir quatre clés: 'title', 'changes', 'intro', et 'outro'. Les valeurs de ces clés doivent être la traduction pure, sans préfixes comme 'Titre:' ou 'Changes:'. Assurez-vous de préserver tous les sauts de ligne originaux (`\\n`) dans la traduction des changements. Corrigez les fautes d'orthographe. Assurez vous de ne pas traduire les mots entourés de ` comme par exemple: `/ping` ou encore les emojis discord sous cette forme: <:blurry_eyes:1399680951704879156> ou <a:blurry_eyes:1399680951704879156>.\n\n" \
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
                    translated_changes = translated_changes.replace('&', CHECKLIST_EMOJI).replace('~', CROSSMARK_EMOJI).replace('£', f"{IN_PROGRESS_EMOJI}") # Appliquer les emojis de checklist et de croix

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
        Gère la soumission du modal. Construit les messages, les envoie dans les canaux appropriés
        (test ou production) et gère la publication.
        """
        await interaction.response.send_message("🚀 Préparation de l'annonce de mise à jour...", ephemeral=True)
        followup_message = await interaction.original_response()

        # --- Sauvegarde de la version ---
        new_version = self.version_number.value
        try:
            with open('version.json', 'w') as f:
                json.dump({'version': new_version}, f, indent=2)
            logging.info(f"Numéro de version mis à jour vers : {new_version}")
        except Exception as e:
            logging.error(f"Impossible de sauvegarder la nouvelle version : {e}")
            await followup_message.edit(content=f"⚠️ Avertissement : Impossible de sauvegarder le nouveau numéro de version `{new_version}`.")
            await asyncio.sleep(3)

        # --- Préparation du contenu ---
        original_title_fr = self.update_name.value
        original_changes_fr = self.changes.value
        original_intro_fr = self.intro_message.value or ""
        original_outro_fr = self.outro_message.value or ""

        await followup_message.edit(content="✨ Correction et traduction du contenu...")
        (corrected_title_fr, corrected_changes_fr, corrected_intro_fr, corrected_outro_fr,
         translated_title, translated_changes, translated_intro, translated_outro) = await self._translate_text(
            original_title_fr, original_changes_fr, original_intro_fr, original_outro_fr
        )

        final_changes_fr_display = corrected_changes_fr.replace('&', f"{CHECKLIST_EMOJI}:").replace('~', f"{CROSSMARK_EMOJI}:").replace('£', f"{IN_PROGRESS_EMOJI}:")
        
        # --- Construction des messages ---
        french_message_content = self._build_message(
            corrected_title_fr, corrected_intro_fr, final_changes_fr_display, corrected_outro_fr, is_english=False
        )
        english_message_content = self._build_message(
            translated_title, translated_intro, translated_changes, translated_outro, is_english=True
        )

        if not (translated_title and translated_changes):
            english_message_content = f"### {CROSSMARK_EMOJI} Translation failed\n\n"
            await followup_message.edit(content="⚠️ Avertissement : La traduction a échoué. Le message anglais ne sera pas complet.")
            await asyncio.sleep(2)

        # --- Préparation des pièces jointes ---
        attachment_data = []
        for attachment in self.attachments:
            try:
                attachment_data.append({'bytes': await attachment.read(), 'filename': attachment.filename})
            except Exception as e:
                logging.error(f"Impossible de lire la pièce jointe {attachment.filename}: {e}")
                await followup_message.edit(content=f"⚠️ Avertissement: Impossible d'attacher le fichier `{attachment.filename}`.")

        # --- Envoi des messages ---
        await followup_message.edit(content="📤 Envoi de l'annonce sur Discord...")
        if self.is_test_run:
            # Mode test : envoi des deux messages dans le canal de test
            test_channel = interaction.guild.get_channel(UPDATE_CHANNEL_ID_TEST)
            if test_channel:
                full_test_message = f"{french_message_content}\n\n---\n\n{english_message_content}"
                await self._send_and_publish(test_channel, full_test_message, attachment_data, followup_message)
            else:
                logging.error(f"Canal de test introuvable (ID: {UPDATE_CHANNEL_ID_TEST})")
                await followup_message.edit(content=f"❌ Erreur: Le canal de test est introuvable.")
        else:
            # Mode production : envoi dans les canaux respectifs
            fr_channel = interaction.guild.get_channel(UPDATE_CHANNEL_ID_FR)
            en_channel = interaction.guild.get_channel(UPDATE_CHANNEL_ID_EN)
            
            if fr_channel:
                await self._send_and_publish(fr_channel, french_message_content, attachment_data, followup_message)
            else:
                logging.error(f"Canal français introuvable (ID: {UPDATE_CHANNEL_ID_FR})")

            if en_channel:
                await self._send_and_publish(en_channel, english_message_content, attachment_data, followup_message)
            else:
                logging.error(f"Canal anglais introuvable (ID: {UPDATE_CHANNEL_ID_EN})")

        await followup_message.edit(content="🎉 L'annonce de mise à jour a été envoyée avec succès !")

    def _build_message(self, title, intro, changes, outro, is_english=False):
        """Construit le contenu du message de mise à jour."""
        greeting = "👋 Hello to the entire community!\n\n" if is_english else "👋 Coucou à toute la communauté !\n\n"
        user_update_msg = f"{TEST_EMOJI} <@1335228717403996160> received an update !\n\n" if is_english else f"{TEST_EMOJI} <@1335228717403996160> a reçu une mise à jour !\n\n"
        conclusion_text = "Stay tuned for future announcements and thank you for your continued support!" if is_english else "Restez connectés pour de futures annonces et merci pour votre soutien continu !"
        team_signature = "The Development Team." if is_english else "L'équipe de développement."

        parts = [f"# {ANNONCE_EMOJI} {title} {ANNONCE_EMOJI}\n\n", greeting]
        if intro:
            parts.append(f"{intro}\n\n")
        parts.extend([user_update_msg, f"{changes}\n\n"])
        if outro:
            parts.append(f"{outro}\n\n")
        parts.append(f"🚀 {conclusion_text} **Utilisez /feedback pour signaler des erreurs ou des bugs ou allez dans <#1350399062418915418>.**\n{team_signature}")
        return "".join(parts)

    async def _send_and_publish(self, channel: discord.TextChannel, content: str, attachment_data: list, followup_message):
        """Envoie un message, le publie si nécessaire, et ajoute une réaction."""
        if not channel:
            return

        def create_files_for_sending():
            return [discord.File(fp=io.BytesIO(item['bytes']), filename=item['filename']) for item in attachment_data]

        try:
            # La logique de division des messages est complexe et peut être omise pour l'instant
            # car les annonces dépassent rarement 2000 caractères. Si nécessaire, elle peut être réintégrée.
            if len(content) > 2000:
                logging.warning("Le contenu du message dépasse 2000 caractères et sera tronqué.")
                content = content[:2000]

            msg = await channel.send(content=content, files=create_files_for_sending())
            
            if channel.is_news():
                try:
                    await msg.publish()
                    logging.info(f"Message publié dans le canal d'annonces {channel.name}.")
                except discord.Forbidden:
                    logging.error(f"Permissions insuffisantes pour publier dans {channel.name}.")
                except Exception as e:
                    logging.error(f"Erreur lors de la publication dans {channel.name}: {e}")

            # Ajout de la réaction
            try:
                verify_emoji = discord.PartialEmoji(name="verify", animated=True, id=1350435235015426130)
                await msg.add_reaction(verify_emoji)
            except Exception as e:
                logging.error(f"Impossible d'ajouter la réaction: {e}")

            # Ghost ping
            try:
                mention = await channel.send("<@&1350428823052746752>")
                await asyncio.sleep(1)
                await mention.delete()
            except Exception as e:
                logging.error(f"Erreur lors du ghost ping: {e}")

        except discord.Forbidden:
            logging.error(f"Permissions insuffisantes pour envoyer des messages dans le canal {channel.name}.")
            await followup_message.edit(content=f"❌ Erreur: Permissions insuffisantes pour le canal {channel.name}.")
        except Exception as e:
            logging.error(f"Erreur inattendue lors de l'envoi dans {channel.name}: {e}", exc_info=True)
            await followup_message.edit(content=f"❌ Une erreur est survenue lors de l'envoi du message.")


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
        attachments="Fichier à joindre à l'annonce (image, document, etc.)",
        test="Envoyer l'annonce sur le canal de test ?"
    )
    @app_commands.choices(
        test=[
            app_commands.Choice(name="Oui", value="oui"),
            app_commands.Choice(name="Non", value="non")
        ]
    )
    @is_owner() # Applique la vérification des propriétaires
    async def update_command(self, interaction: discord.Interaction, test: str,  attachments: discord.Attachment = None):
        """
        Commande slash /update pour déclencher le modal de mise à jour.
        Détermine si l'envoi est un test ou une publication réelle.
        """
        files_for_modal = []
        if attachments:
            files_for_modal.append(attachments)

        # Déterminer si c'est un test
        is_test = (test == "oui")

        # Passer le booléen de test au modal
        modal = UpdateModal(attachments=files_for_modal, is_test_run=is_test)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="patch-note", description="[🤖 Dev] Déploie un patch et incrémente la version.")
    @is_owner()
    async def patch_note_command(self, interaction: discord.Interaction):
        """
        Annonce un patch, incrémente la version et notifie les canaux appropriés.
        """
        await interaction.response.defer(ephemeral=True)

        try:
            # --- 1. Lire la version actuelle ---
            with open('version.json', 'r') as f:
                data = json.load(f)
                current_version = data.get('version', '1.0.0')

            # --- 2. Incrémenter la version ---
            parts = current_version.split('.')
            if len(parts) != 3 or not all(p.isdigit() for p in parts):
                await interaction.followup.send(f"❌ Erreur : Le format de la version `{current_version}` est invalide. Il doit être de type `X.Y.Z`.", ephemeral=True)
                return

            patch_number = int(parts[2])
            new_patch_number = patch_number + 1
            new_version = f"{parts[0]}.{parts[1]}.{new_patch_number}"

            # --- 3. Mettre à jour le fichier JSON ---
            with open('version.json', 'w') as f:
                json.dump({'version': new_version}, f, indent=2)

            logging.info(f"Version incrémentée de {current_version} à {new_version}")

            # --- 4. Envoyer les notifications ---
            french_channel_id = 1345064533173080166
            english_channel_id = 1421773639761526824

            french_channel = self.bot.get_channel(french_channel_id)
            english_channel = self.bot.get_channel(english_channel_id)

            message_fr = f"**⚙️ Patch Déployé !**\n\nUn nouveau patch vient d'être appliqué. La version est maintenant la **{new_version}**."
            message_en = f"**⚙️ Patch Deployed!**\n\nA new patch has just been applied. The version is now **{new_version}**."

            if french_channel:
                await french_channel.send(message_fr)
            else:
                logging.warning(f"Canal français introuvable (ID: {french_channel_id})")

            if english_channel:
                await english_channel.send(message_en)
            else:
                logging.warning(f"Canal anglais introuvable (ID: {english_channel_id})")

            await interaction.followup.send(f"✅ Le patch **{new_version}** a été annoncé avec succès.", ephemeral=True)

        except FileNotFoundError:
            await interaction.followup.send("❌ Erreur : Le fichier `version.json` est introuvable. Veuillez d'abord utiliser `/update` pour le créer.", ephemeral=True)
        except (json.JSONDecodeError, Exception) as e:
            logging.error(f"Erreur dans la commande /patch-note : {e}", exc_info=True)
            await interaction.followup.send(f"❌ Une erreur inattendue est survenue : {e}", ephemeral=True)


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
