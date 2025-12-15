import asyncio
import contextlib
import io
import json
import logging
import os

import discord
from discord import app_commands, ui
from discord.ext import commands
from dotenv import load_dotenv
from google import genai
from google.genai import types

import PARAM

# Configurez le logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

load_dotenv()

# Récupération de la clé API Gemini depuis les variables d'environnement
gemini_api_key = os.getenv("GEMINI_API")

# Client instance
if gemini_api_key:
    client = genai.Client(api_key=gemini_api_key)
else:
    client = None
    logging.warning("GEMINI_API key not found. AI features will be disabled.")

# --- Helpers ---


def _split_message(content: str, limit: int = 2000) -> list[str]:
    """Découpe un message en morceaux de `limit` caractères maximum."""
    if len(content) <= limit:
        return [content]

    chunks = []
    while content:
        if len(content) <= limit:
            chunks.append(content)
            break

        # Tenter de couper au dernier saut de ligne avant la limite
        split_index = content.rfind("\n", 0, limit)
        if split_index == -1:
            # Pas de saut de ligne, on coupe au dernier espace
            split_index = content.rfind(" ", 0, limit)

        if split_index == -1:
            # Pas d'espace non plus, on coupe brut
            split_index = limit

        chunks.append(content[:split_index])
        content = content[
            split_index:
        ].lstrip()  # On retire les espaces/sauts de ligne au début du morceau suivant

    return chunks


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
        chunks = _split_message(content)

        # On n'envoie les fichiers qu'avec le dernier message
        for i, chunk in enumerate(chunks):
            current_files = files if i == len(chunks) - 1 else None

            msg = await channel.send(content=chunk, files=current_files)

            if channel.is_news():
                try:
                    await msg.publish()
                    logging.info(
                        f"Message publié dans le canal d'annonces {channel.name}."
                    )
                except discord.Forbidden:
                    logging.error(
                        f"Permissions insuffisantes pour publier dans {channel.name}."
                    )
                except Exception as e:
                    logging.error(
                        f"Erreur lors de la publication dans {channel.name}: {e}"
                    )

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


async def _call_gemini_api(prompt: str, schema: dict) -> dict | None:
    """Appelle l'API Gemini avec une nouvelle tentative en cas d'échec."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = await asyncio.to_thread(
                lambda: client.models.generate_content(
                    model=f"{PARAM.GEMINI_MODEL}",
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=schema,
                    ),
                )
            )

            if response.text:
                try:
                    return json.loads(response.text)
                except (ValueError, json.JSONDecodeError) as e:
                    logging.error(
                        f"Error parsing JSON from Gemini: {e}\nResponse received: {response.text}"
                    )
                    return None
            else:
                logging.warning("Structure de réponse de l'API Gemini inattendue.")
                return None

        except Exception as e:
            logging.error(
                f"Erreur API Gemini (tentative {attempt + 1}/{max_retries}): {e}"
            )
            await asyncio.sleep(2**attempt)

    logging.error(f"Échec de l'appel à l'API Gemini après {max_retries} tentatives.")
    return None


async def _correct_french_text(text_parts: dict) -> dict:
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
    corrected_data = await _call_gemini_api(prompt, schema)
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


async def _translate_to_english(text_parts: dict) -> dict:
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
    translated_data = await _call_gemini_api(prompt, schema)
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
            changes.replace("&", f"- {PARAM.checkmark}")
            .replace("~", f"- {PARAM.crossmarck}")
            .replace("£", f"- {PARAM.in_progress}")
        )
        user_update_msg = f"<@{PARAM.BOT_ID}> received an update ! {PARAM.test}\n\n"
        conclusion_text = "Stay tuned for future announcements and thank you for your continued support!"
        team_signature = "The Development Team."
        feedback_prompt = "Use /feedback to report any mistakes or bugs or go to <#1350399062418915418>."
    else:
        changes = (
            changes.replace("&", f"- {PARAM.checkmark}:")
            .replace("~", f"- {PARAM.crossmarck}:")
            .replace("£", f"- {PARAM.in_progress}:")
        )
        user_update_msg = f"<@{PARAM.BOT_ID}> a reçu une mise à jour ! {PARAM.test}\n\n"
        conclusion_text = "Restez connectés pour de futures annonces et merci pour votre soutien continu !"
        team_signature = "L'équipe de développement."
        feedback_prompt = "Utilisez /feedback pour signaler des erreurs ou des bugs ou allez dans <#1350399062418915418>."

    parts = [f"# {PARAM.annonce} {title} {PARAM.annonce}\n\n"]
    if intro:
        parts.append(f"{intro}\n\n")
    parts.extend([user_update_msg, f"{changes}\n\n"])
    if outro:
        parts.append(f"{outro}\n\n")
    parts.append(f"🚀 {conclusion_text} **{feedback_prompt}**\n{team_signature}")
    return "".join(parts)


class EditUpdateModal(ui.Modal):
    """Modal pour éditer le texte de la mise à jour (FR ou EN)."""

    def __init__(
        self, texts: dict, is_english: bool, view: "UpdateManagerView"
    ) -> None:
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

    async def on_submit(self, interaction: discord.Interaction) -> None:
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
    ) -> None:
        super().__init__(timeout=None)
        self.fr_texts = fr_texts
        self.en_texts = en_texts
        self.files_data = files_data  # List of (filename, bytes)
        self.original_interaction = original_interaction

    async def refresh_message(self, interaction: discord.Interaction) -> None:
        """Met à jour le message de test avec les nouvelles données."""
        french_message = _build_message(self.fr_texts, is_english=False)
        english_message = _build_message(self.en_texts, is_english=True)
        full_test_message = f"{french_message}\n\n---\n\n{english_message}"

        chunks = _split_message(full_test_message)

        # Helper pour recréer les fichiers (les objets File sont consommés à l'envoi)
        def get_files() -> list[discord.File]:
            files = []
            for filename, file_bytes in self.files_data:
                files.append(discord.File(io.BytesIO(file_bytes), filename=filename))
            return files

        # Si un seul morceau, on édite simplement le message existant
        if len(chunks) == 1:
            if not interaction.response.is_done():
                await interaction.response.edit_message(
                    content=chunks[0], attachments=get_files(), view=self
                )
            else:
                await interaction.edit_original_response(
                    content=chunks[0], attachments=get_files(), view=self
                )
            return

        # Si plusieurs morceaux, on doit supprimer l'ancien message et en envoyer de nouveaux
        # car on ne peut pas transformer un message en plusieurs via edit
        if not interaction.response.is_done():
            await interaction.response.defer()

        # Supprimer l'ancien message (celui qui contient les boutons)
        if interaction.message:
            with contextlib.suppress(discord.HTTPException, discord.Forbidden):
                await interaction.message.delete()

        channel = interaction.channel
        if not channel:
            # Fallback (peu probable)
            await interaction.followup.send(
                "❌ Erreur: Canal introuvable pour le rafraîchissement.", ephemeral=True
            )
            return

        for i, chunk in enumerate(chunks):
            is_last = i == len(chunks) - 1
            current_view = self if is_last else None
            current_files = get_files() if is_last else None

            await channel.send(content=chunk, files=current_files, view=current_view)

    @ui.button(label="Envoyer Production", style=discord.ButtonStyle.green)
    async def send_prod(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
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

        # Re-create files for EN
        files_en = []
        for filename, file_bytes in self.files_data:
            files_en.append(discord.File(io.BytesIO(file_bytes), filename=filename))

        await _send_and_publish(en_channel, english_message, files_en)
        await _ghost_ping(en_channel)

        await interaction.followup.send(
            "✅ Mise à jour déployée en production !", ephemeral=True
        )

    @ui.button(label="Éditer FR", style=discord.ButtonStyle.blurple)
    async def edit_fr(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        await interaction.response.send_modal(
            EditUpdateModal(self.fr_texts, is_english=False, view=self)
        )

    @ui.button(label="Éditer EN", style=discord.ButtonStyle.blurple)
    async def edit_en(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        await interaction.response.send_modal(
            EditUpdateModal(self.en_texts, is_english=True, view=self)
        )

    @ui.button(label="Annuler", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.send_message(
            "❌ Mise à jour annulée.", ephemeral=True
        )
        # Disable buttons
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)


class UpdateModal(ui.Modal, title="Nouvelle Mise à Jour"):
    """Modal Discord pour collecter les informations d'une nouvelle mise à jour."""

    def __init__(self, attachments: list[discord.Attachment]) -> None:
        super().__init__()
        self.attachments = attachments
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

        corrected_texts = await _correct_french_text(original_texts)
        translated_texts = await _translate_to_english(corrected_texts)

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
            files_objects.append(
                discord.File(io.BytesIO(file_bytes), filename=filename)
            )

        french_message = _build_message(corrected_texts, is_english=False)
        english_message = _build_message(translated_texts, is_english=True)
        full_test_message = f"{french_message}\n\n---\n\n{english_message}"

        await followup_message.edit(
            content="📤 Envoi de la prévisualisation sur le canal test..."
        )

        test_channel = interaction.guild.get_channel(PARAM.UPDATE_CHANNEL_ID_TEST)

        if not test_channel:
            await followup_message.edit(
                content="❌ Erreur: Le canal de test est introuvable. Vérifiez l'ID dans PARAM.py."
            )
            return

        view = UpdateManagerView(
            corrected_texts, translated_texts, files_data, interaction
        )

        chunks = _split_message(full_test_message)

        for i, chunk in enumerate(chunks):
            # On attache la vue et les fichiers uniquement au dernier message
            is_last = i == len(chunks) - 1
            current_view = view if is_last else None
            current_files = files_objects if is_last else None

            await test_channel.send(
                content=chunk, files=current_files, view=current_view
            )

        await followup_message.edit(
            content="🎉 Prévisualisation envoyée ! Vérifiez le canal test."
        )

    def _save_version(self) -> None:
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
    @app_commands.describe(attachments="Fichier à joindre.")
    @is_owner()
    async def update_command(
        self,
        interaction: discord.Interaction,
        attachments: discord.Attachment | None = None,
    ) -> None:
        files = [attachments] if attachments else []
        await interaction.response.send_modal(UpdateModal(attachments=files))

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
