import asyncio
import io
import json
import logging
import os

import discord
from discord import app_commands, ui
from discord.ext import commands
from dotenv import load_dotenv
import requests

import PARAM

# Configurez le logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

load_dotenv()

# Récupération de la clé API Gemini depuis les variables d'environnement
gemini_api_key = os.getenv("GEMINI_API")

# --- Helpers ---


def is_owner():
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


async def _ghost_ping(channel: discord.TextChannel) -> None:
    """Envoie une mention de rôle supprimée rapidement."""
    if not channel:
        return
    try:
        mention = await channel.send(f"<@&{PARAM.UPDATE_ROLE_ID}>")
        await asyncio.sleep(1)
        await mention.delete()
    except Exception as e:
        logging.error(f"Erreur lors du ghost ping dans {channel.name}: {e}")


async def _send_and_publish(
    channel: discord.TextChannel,
    content: str,
    files: list[discord.File] | None = None,
    followup_message: discord.WebhookMessage | None = None,
) -> None:
    """Envoie un message, le publie si nécessaire, et ajoute une réaction."""
    if not channel:
        logging.error("Tentative d'envoi à un canal non valide.")
        if followup_message:
            await followup_message.edit(content="❌ Erreur: Le canal est introuvable.")
        return

    try:
        if len(content) > 2000:
            logging.warning(
                "Le contenu du message dépasse 2000 caractères et sera tronqué."
            )
            content = content[:2000]

        msg = await channel.send(content=content, files=files)

        if channel.is_news():
            try:
                await msg.publish()
                logging.info(f"Message publié dans le canal d'annonces {channel.name}.")
            except discord.Forbidden:
                logging.error(
                    f"Permissions insuffisantes pour publier dans {channel.name}."
                )
            except Exception as e:
                logging.error(f"Erreur lors de la publication dans {channel.name}: {e}")

        try:
            verify_emoji = discord.PartialEmoji(
                name="verify", animated=True, id=1350435235015426130
            )
            await msg.add_reaction(verify_emoji)
        except Exception as e:
            logging.error(f"Impossible d'ajouter la réaction: {e}")

    except discord.Forbidden:
        logging.error(
            f"Permissions insuffisantes pour envoyer des messages dans {channel.name}."
        )
        if followup_message:
            await followup_message.edit(
                content=f"❌ Erreur: Permissions insuffisantes pour le canal {channel.name}."
            )
    except Exception as e:
        logging.error(
            f"Erreur inattendue lors de l'envoi dans {channel.name}: {e}", exc_info=True
        )
        if followup_message:
            await followup_message.edit(
                content="❌ Une erreur est survenue lors de l'envoi du message."
            )


# --- Translation and Correction ---


async def _call_gemini_api(prompt: str, schema: dict, api_url: str) -> dict | None:
    """Appelle l'API Gemini avec une nouvelle tentative en cas d'échec."""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = await asyncio.to_thread(
                lambda: requests.post(
                    api_url,
                    headers={"Content-Type": "application/json"},
                    data=json.dumps(payload),
                )
            )
            response.raise_for_status()
            result = response.json()
            if (
                result.get("candidates")
                and result["candidates"][0].get("content")
                and result["candidates"][0]["content"].get("parts")
            ):
                json_str = result["candidates"][0]["content"]["parts"][0]["text"]

                # Extrait le JSON même s'il est enrobé dans du Markdown
                try:
                    json_start = json_str.index("{")
                    json_end = json_str.rindex("}") + 1
                    json_str = json_str[json_start:json_end]
                    return json.loads(json_str)
                except (ValueError, json.JSONDecodeError) as e:
                    logging.error(
                        f"Error parsing JSON from Gemini: {e}\nResponse received: {json_str}"
                    )
                    return None
            else:
                logging.warning("Structure de réponse de l'API Gemini inattendue.")
                return None
        except requests.exceptions.RequestException as e:
            logging.error(
                f"Erreur API Gemini (tentative {attempt + 1}/{max_retries}): {e}"
            )
            await asyncio.sleep(2**attempt)
        except json.JSONDecodeError as e:
            logging.error(f"Erreur de décodage JSON de la réponse Gemini: {e}")
            return None
        except Exception as e:
            logging.error(
                f"Erreur inattendue lors de l'appel à l'API Gemini: {e}", exc_info=True
            )
            return None
    logging.error(f"Échec de l'appel à l'API Gemini après {max_retries} tentatives.")
    return None


async def _correct_french_text(text_parts: dict, api_url: str) -> dict:
    """Corrige le texte français en utilisant l'API Gemini."""
    prompt = (
        "Agis comme un correcteur orthographique et grammatical expert. Corrige le texte français suivant. "
        "Règles strictes :\n"
        "1. Réponds uniquement avec un objet JSON valide contenant les clés : 'corrected_title', 'corrected_changes', 'corrected_intro', et 'corrected_outro'.\n"
        "2. PRÉSERVE scrupuleusement la mise en forme, TOUS les sauts de ligne (\n), et les caractères spéciaux (&, ~, £).\n"
        "3. NE CHANGE PAS les mots techniques, les noms propres, ou les termes que tu ne connais pas. Si tu as un doute, garde le mot original.\n"
        "4. Ne change pas le sens des phrases.\n\n"
        f"Titre: {text_parts['title']}\n"
        f"Changements: {text_parts['changes']}\n"
        f"Introduction: {text_parts['intro']}\n"
        f"Conclusion: {text_parts['outro']}"
    )
    schema = {
        "type": "OBJECT",
        "properties": {
            "corrected_title": {"type": "STRING"},
            "corrected_changes": {"type": "STRING"},
            "corrected_intro": {"type": "STRING"},
            "corrected_outro": {"type": "STRING"},
        },
        "required": [
            "corrected_title",
            "corrected_changes",
            "corrected_intro",
            "corrected_outro",
        ],
    }
    corrected_data = await _call_gemini_api(prompt, schema, api_url)
    if corrected_data:
        logging.info("Correction française réussie.")
        return {
            "title": corrected_data.get("corrected_title", text_parts["title"]),
            "changes": corrected_data.get(
                "corrected_changes", text_parts["changes"]
            ).replace("\\n", "\n"),
            "intro": corrected_data.get("corrected_intro", text_parts["intro"]),
            "outro": corrected_data.get("corrected_outro", text_parts["outro"]),
        }
    logging.warning("Échec de la correction, utilisation du texte original.")
    return text_parts


async def _translate_to_english(text_parts: dict, api_url: str) -> dict:
    """Traduit le texte en anglais en utilisant l'API Gemini."""
    prompt = (
        "Agis comme un traducteur expert du français vers l'anglais. Traduis le texte suivant.\n"
        "Règles strictes :\n"
        "1. Réponds uniquement avec un objet JSON valide contenant les clés : 'title', 'changes', 'intro', 'outro'.\n"
        "2. PRÉSERVE scrupuleusement la mise en forme et TOUS les sauts de ligne (\n).\n"
        "3. NE TRADUIS PAS les mots entre `code`, les variables, ou les emojis Discord (<:...:...>).\n"
        "4. Conserve les termes techniques inchangés si une traduction directe n'est pas évidente.\n\n"
        f"Titre original: {text_parts['title']}\n"
        f"Changements originaux: {text_parts['changes']}\n"
        f"Introduction originale: {text_parts['intro']}\n"
        f"Conclusion originale: {text_parts['outro']}"
    )
    schema = {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING"},
            "changes": {"type": "STRING"},
            "intro": {"type": "STRING"},
            "outro": {"type": "STRING"},
        },
        "required": ["title", "changes", "intro", "outro"],
    }
    translated_data = await _call_gemini_api(prompt, schema, api_url)
    if translated_data:
        logging.info("Traduction anglaise réussie.")
        return {
            "title": translated_data.get("title", ""),
            "changes": translated_data.get("changes", "").replace("\\n", "\n"),
            "intro": translated_data.get("intro", ""),
            "outro": translated_data.get("outro", ""),
        }
    logging.error("Échec de la traduction.")
    return {"title": "", "changes": "", "intro": "", "outro": ""}


def _build_message(texts: dict, is_english: bool) -> str:
    """Construit le contenu du message de mise à jour."""
    title, intro, changes, outro = (
        texts["title"],
        texts["intro"],
        texts["changes"],
        texts["outro"],
    )

    if is_english:
        changes = (
            changes.replace("&", PARAM.checkmark)
            .replace("~", PARAM.crossmarck)
            .replace("£", PARAM.in_progress)
        )
        greeting = "👋 Hello to the entire community!\n\n"
        user_update_msg = f"{PARAM.test} <@{PARAM.BOT_ID}> received an update !\n\n"
        conclusion_text = "Stay tuned for future announcements and thank you for your continued support!"
        team_signature = "The Development Team."
        feedback_prompt = "Use /feedback to report any mistakes or bugs or go to <#1350399062418915418>."
    else:
        changes = (
            changes.replace("&", f"{PARAM.checkmark}:")
            .replace("~", f"{PARAM.crossmarck}:")
            .replace("£", f"{PARAM.in_progress}:")
        )
        greeting = "👋 Coucou à toute la communauté !\n\n"
        user_update_msg = f"{PARAM.test} <@{PARAM.BOT_ID}> a reçu une mise à jour !\n\n"
        conclusion_text = "Restez connectés pour de futures annonces et merci pour votre soutien continu !"
        team_signature = "L'équipe de développement."
        feedback_prompt = "Utilisez /feedback pour signaler des erreurs ou des bugs ou allez dans <#1350399062418915418>."

    parts = [f"# {PARAM.annonce} {title} {PARAM.annonce}\n\n", greeting]
    if intro:
        parts.append(f"{intro}\n\n")
    parts.extend([user_update_msg, f"{changes}\n\n"])
    if outro:
        parts.append(f"{outro}\n\n")
    parts.append(f"🚀 {conclusion_text} **{feedback_prompt}**\n{team_signature}")
    return "".join(parts)


class EditUpdateModal(ui.Modal):
    """Modal pour éditer le texte de la mise à jour (FR ou EN)."""

    def __init__(self, texts: dict, is_english: bool, view: "UpdateManagerView"):
        title = "Éditer texte (Anglais)" if is_english else "Éditer texte (Français)"
        super().__init__(title=title)
        self.texts = texts
        self.is_english = is_english
        self.view_ref = view

        self.title_input = ui.TextInput(
            label="Titre", default=texts.get("title", ""), required=True
        )
        self.intro_input = ui.TextInput(
            label="Introduction",
            default=texts.get("intro", ""),
            style=discord.TextStyle.paragraph,
            required=False,
        )
        self.changes_input = ui.TextInput(
            label="Changements",
            default=texts.get("changes", ""),
            style=discord.TextStyle.paragraph,
            required=True,
        )
        self.outro_input = ui.TextInput(
            label="Conclusion",
            default=texts.get("outro", ""),
            style=discord.TextStyle.paragraph,
            required=False,
        )

        self.add_item(self.title_input)
        self.add_item(self.intro_input)
        self.add_item(self.changes_input)
        self.add_item(self.outro_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_texts = {
            "title": self.title_input.value,
            "intro": self.intro_input.value,
            "changes": self.changes_input.value,
            "outro": self.outro_input.value,
        }

        if self.is_english:
            self.view_ref.en_texts = new_texts
        else:
            self.view_ref.fr_texts = new_texts

        await self.view_ref.refresh_message(interaction)


class UpdateManagerView(ui.View):
    """Vue pour gérer l'envoi de la mise à jour (Modifier / Envoyer Production)."""

    def __init__(
        self,
        fr_texts: dict,
        en_texts: dict,
        files_data: list[tuple[str, bytes]],
        original_interaction: discord.Interaction,
    ):
        super().__init__(timeout=None)
        self.fr_texts = fr_texts
        self.en_texts = en_texts
        self.files_data = files_data  # List of (filename, bytes)
        self.original_interaction = original_interaction

    async def refresh_message(self, interaction: discord.Interaction):
        """Met à jour le message de test avec les nouvelles données."""
        french_message = _build_message(self.fr_texts, is_english=False)
        english_message = _build_message(self.en_texts, is_english=True)
        full_test_message = f"{french_message}\n\n---\n\n{english_message}"

        # Re-create files from bytes
        files = []
        for filename, file_bytes in self.files_data:
            files.append(discord.File(io.BytesIO(file_bytes), filename=filename))

        # If we are replying to the interaction (Modal submit), we use response.edit_message
        if not interaction.response.is_done():
            await interaction.response.edit_message(
                content=full_test_message, attachments=files, view=self
            )
        else:
            # Fallback
            await interaction.edit_original_response(
                content=full_test_message, attachments=files, view=self
            )

    @ui.button(label="Envoyer Production", style=discord.ButtonStyle.green)
    async def send_prod(
        self, interaction: discord.Interaction, button: ui.Button
    ):
        await interaction.response.defer()

        # Disable buttons to prevent double click
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)

        fr_channel = interaction.guild.get_channel(PARAM.UPDATE_CHANNEL_ID_FR)
        en_channel = interaction.guild.get_channel(PARAM.UPDATE_CHANNEL_ID_EN)

        french_message = _build_message(self.fr_texts, is_english=False)
        english_message = _build_message(self.en_texts, is_english=True)

        # Re-create files for FR
        files_fr = []
        for filename, file_bytes in self.files_data:
            files_fr.append(discord.File(io.BytesIO(file_bytes), filename=filename))

        await _send_and_publish(fr_channel, french_message, files_fr)
        await _ghost_ping(fr_channel)

        # Re-create files for EN (or send without files as before?)
        # The original code said: # On ne re-upload pas les fichiers pour le 2ème message
        # So we send EN without files.
        await _send_and_publish(en_channel, english_message, None)
        await _ghost_ping(en_channel)

        await interaction.followup.send("✅ Mise à jour déployée en production !", ephemeral=True)

    @ui.button(label="Éditer FR", style=discord.ButtonStyle.blurple)
    async def edit_fr(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(
            EditUpdateModal(self.fr_texts, is_english=False, view=self)
        )

    @ui.button(label="Éditer EN", style=discord.ButtonStyle.blurple)
    async def edit_en(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(
            EditUpdateModal(self.en_texts, is_english=True, view=self)
        )

    @ui.button(label="Annuler", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("❌ Mise à jour annulée.", ephemeral=True)
        # Disable buttons
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)


class UpdateModal(ui.Modal, title="Nouvelle Mise à Jour"):
    """Modal Discord pour collecter les informations d'une nouvelle mise à jour."""

    def __init__(self, attachments: list[discord.Attachment]) -> None:
        super().__init__()
        self.attachments = attachments
        self.api_url_gemini = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_api_key}"
        try:
            with open("version.json") as f:
                self.version_number.default = json.load(f).get("version", "1.0.0")
        except (FileNotFoundError, json.JSONDecodeError):
            self.version_number.default = "1.0.0"

    update_name = ui.TextInput(
        label="Nom de la Mise à Jour (ex: v1.2.3)", max_length=100, required=True
    )
    version_number = ui.TextInput(
        label="Numéro de version (ex: 1.0.1)", max_length=20, required=True
    )
    intro_message = ui.TextInput(
        label="Message d'introduction (facultatif)", max_length=500, required=False
    )
    changes = ui.TextInput(
        label="Qu'est-ce qui a changé ? &:✅ / ~:❌ / £:⏳",
        style=discord.TextStyle.paragraph,
        max_length=2000,
        required=True,
    )
    outro_message = ui.TextInput(
        label="Message de conclusion (facultatif)", max_length=500, required=False
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        """Gère la soumission du modal."""
        await interaction.response.send_message(
            "🚀 Préparation de l'annonce...", ephemeral=True
        )
        followup_message = await interaction.original_response()

        self._save_version()

        await followup_message.edit(content="✨ Correction et traduction du contenu...")

        original_texts = {
            "title": self.update_name.value,
            "changes": self.changes.value,
            "intro": self.intro_message.value or "",
            "outro": self.outro_message.value or "",
        }

        corrected_texts = await _correct_french_text(
            original_texts, self.api_url_gemini
        )
        translated_texts = await _translate_to_english(
            corrected_texts, self.api_url_gemini
        )

        if not translated_texts.get("title") or not translated_texts.get("changes"):
            await followup_message.edit(
                content="⚠️ La traduction a échoué. Le message anglais sera incomplet."
            )
            await asyncio.sleep(2)

        # Read files into memory (bytes) to persist them
        files_data = []
        for attachment in self.attachments:
            try:
                data = await attachment.read()
                files_data.append((attachment.filename, data))
            except Exception as e:
                logging.error(f"Error reading attachment {attachment.filename}: {e}")

        # Prepare files for the test message
        files_objects = []
        for filename, file_bytes in files_data:
            files_objects.append(discord.File(io.BytesIO(file_bytes), filename=filename))

        french_message = _build_message(corrected_texts, is_english=False)
        english_message = _build_message(translated_texts, is_english=True)
        full_test_message = f"{french_message}\n\n---\n\n{english_message}"

        await followup_message.edit(content="📤 Envoi de la prévisualisation sur le canal test...")

        test_channel = interaction.guild.get_channel(PARAM.UPDATE_CHANNEL_ID_TEST)

        view = UpdateManagerView(corrected_texts, translated_texts, files_data, interaction)

        await test_channel.send(
            content=full_test_message,
            files=files_objects,
            view=view
        )
        await _ghost_ping(test_channel)

        await followup_message.edit(content="🎉 Prévisualisation envoyée ! Vérifiez le canal test.")

    def _save_version(self):
        try:
            with open("version.json", "w") as f:
                json.dump({"version": self.version_number.value}, f, indent=2)
            logging.info(f"Version mise à jour vers : {self.version_number.value}")
        except OSError as e:
            logging.error(f"Impossible de sauvegarder la version : {e}")


class ManagementCog(commands.Cog):
    """Cog pour les commandes de gestion du bot."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="update", description="[🤖 Dev] Envoie une annonce de mise à jour."
    )
    @app_commands.describe(
        attachments="Fichier à joindre."
    )
    @is_owner()
    async def update_command(
        self,
        interaction: discord.Interaction,
        attachments: discord.Attachment | None = None,
    ) -> None:
        files = [attachments] if attachments else []
        await interaction.response.send_modal(
            UpdateModal(attachments=files)
        )

    @app_commands.command(
        name="patch-note",
        description="[🤖 Dev] Déploie un patch et incrémente la version.",
    )
    @is_owner()
    async def patch_note_command(self, interaction: discord.Interaction) -> None:
        """Annonce un patch, incrémente la version et notifie les canaux."""
        await interaction.response.defer(ephemeral=True)
        try:
            with open("version.json", "r+") as f:
                data = json.load(f)
                current_version = data.get("version", "1.0.0")

                parts = current_version.split(".")
                if len(parts) != 3 or not all(p.isdigit() for p in parts):
                    await interaction.followup.send(
                        f"❌ Format de version invalide: `{current_version}`.",
                        ephemeral=True,
                    )
                    return

                new_version = f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
                data["version"] = new_version

                f.seek(0)
                json.dump(data, f, indent=2)
                f.truncate()
            logging.info(f"Version incrémentée à {new_version}")

        except FileNotFoundError:
            await interaction.followup.send(
                "❌ `version.json` introuvable. Utilisez `/update` d'abord.",
                ephemeral=True,
            )
            return
        except (json.JSONDecodeError, KeyError) as e:
            await interaction.followup.send(
                f"❌ Erreur de lecture de `version.json`: {e}", ephemeral=True
            )
            return

        fr_channel = self.bot.get_channel(PARAM.UPDATE_CHANNEL_ID_FR)
        en_channel = self.bot.get_channel(PARAM.UPDATE_CHANNEL_ID_EN)

        message_fr = f"**⚙️ Patch Déployé !**\n\nUn nouveau patch vient d'être appliqué. La version est maintenant la **{new_version}**."
        message_en = f"**⚙️ Patch Deployed!**\n\nA new patch has just been applied. The version is now **{new_version}**."

        await _send_and_publish(fr_channel, message_fr)
        await _ghost_ping(fr_channel)
        await _send_and_publish(en_channel, message_en)
        await _ghost_ping(en_channel)

        await interaction.followup.send(
            f"✅ Patch **{new_version}** annoncé.", ephemeral=True
        )

    @update_command.error
    async def update_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Gestionnaire d'erreurs pour la commande /update."""
        message = f"Une erreur est survenue: {error}"
        if isinstance(error, app_commands.CheckFailure):
            return  # Déjà géré par le check
        elif isinstance(error, app_commands.CommandOnCooldown):
            message = f"Commande en cooldown. Réessayez dans {error.retry_after:.1f}s."
        else:
            logging.error(f"Erreur inattendue dans /update: {error}", exc_info=True)

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ManagementCog(bot))
