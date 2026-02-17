import asyncio
from collections.abc import Callable
import contextlib
import io
import json
import logging
import os

import discord
from discord import app_commands, ui
from discord.ext import commands
from google import genai
from google.genai import types

import PARAM

# Configurez le logging

# Récupération de la clé API Gemini depuis les variables d'environnement
gemini_api_key = os.getenv("GEMINI_API")

# Client instance
if gemini_api_key:
    client = genai.Client(api_key=gemini_api_key)
else:
    client = None
    logging.warning("GEMINI_API key not found. AI features will be disabled.")


# --- Helpers (Matched with cog/maj.py) ---


def _split_message(content: str, limit: int = 2000) -> list[str]:
    """Découpe un message en morceaux de `limit` caractères maximum."""
    if len(content) <= limit:
        return [content]

    chunks = []
    while content:
        if len(content) <= limit:
            chunks.append(content)
            break
        split_index = content.rfind("\n", 0, limit)
        if split_index == -1:
            split_index = content.rfind(" ", 0, limit)
        if split_index == -1:
            split_index = limit
        chunks.append(content[:split_index])
        content = content[split_index:].lstrip()
    return chunks


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
    if not client:
        logging.error("Client Gemini non initialisé (Clé API manquante ?).")
        return None

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
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                logging.warning(
                    "Quota API Gemini atteint (429). Abandon de l'IA pour cette requête."
                )
                return None

            logging.error(
                f"Erreur API Gemini (tentative {attempt + 1}/{max_retries}): {e}"
            )
            await asyncio.sleep(2**attempt)
    logging.error(f"Échec de l'appel à l'API Gemini après {max_retries} tentatives.")
    return None


async def _correct_french_text(text_parts: dict) -> dict:
    """Corrige le texte français du patch note en utilisant l'API Gemini."""
    prompt = (
        "Agis comme un correcteur orthographique et grammatical expert. Corrige le texte français suivant. "
        "Règles strictes :\n"
        "1. Réponds uniquement avec un objet JSON valide contenant les clés : 'corrected_changes'.\n"
        "2. Le contenu de 'corrected_changes' doit être UNIQUEMENT le texte corrigé, SANS titre, SANS préfixe (comme 'Changements:'), et SANS guillemets supplémentaires.\n"
        "3. PRÉSERVE scrupuleusement la mise en forme, TOUS les sauts de ligne (\n), et les caractères spéciaux.\n"
        "4. NE CHANGE PAS les mots techniques, les noms propres, ou les termes que tu ne connais pas.\n\n"
        f"Texte à corriger :\n{text_parts['changes']}"
    )
    schema = {
        "type": "OBJECT",
        "properties": {
            "corrected_changes": {"type": "STRING"},
        },
        "required": [
            "corrected_changes",
        ],
    }
    corrected_data = await _call_gemini_api(prompt, schema)
    if corrected_data:
        logging.info("Correction française réussie.")
        return {
            "changes": corrected_data.get(
                "corrected_changes", text_parts["changes"]
            ).replace("\\n", "\n"),
        }
    logging.warning("Échec de la correction, utilisation du texte original.")
    return text_parts


async def _translate_to_english(text_parts: dict) -> dict:
    """Traduit le texte du patch note en anglais en utilisant l'API Gemini."""
    prompt = (
        "Agis comme un traducteur expert du français vers l'anglais. Traduis le texte suivant.\n"
        "Règles strictes :\n"
        "1. Réponds uniquement avec un objet JSON valide contenant les clés : 'changes'.\n"
        "2. Le contenu de 'changes' doit être UNIQUEMENT le texte traduit, SANS titre, SANS préfixe (comme 'Changes:'), et SANS guillemets supplémentaires.\n"
        "3. PRÉSERVE scrupuleusement la mise en forme et TOUS les sauts de ligne (\n).\n"
        "4. NE TRADUIS PAS les mots entre `code`, les variables, ou les emojis Discord (<:...:...>).\n"
        "5. Conserve les termes techniques inchangés si une traduction directe n'est pas évidente.\n\n"
        f"Texte à traduire :\n{text_parts['changes']}"
    )
    schema = {
        "type": "OBJECT",
        "properties": {
            "changes": {"type": "STRING"},
        },
        "required": ["changes"],
    }
    translated_data = await _call_gemini_api(prompt, schema)
    if translated_data:
        logging.info("Traduction anglaise réussie.")
        return {
            "changes": translated_data.get("changes", "").replace("\\n", "\n"),
        }
    logging.error("Échec de la traduction.")
    return {"changes": ""}


def _build_message(texts: dict, version: str, is_english: bool) -> str:
    """Construit le contenu du message de patch note."""
    changes = texts["changes"]

    if is_english:
        header = f"**⚙️ Patch Deployed!**\n\nA new patch has just been applied. The version is now **{version}**."
    else:
        header = f"**⚙️ Patch Déployé !**\n\nUn nouveau patch vient d'être appliqué. La version est maintenant la **{version}**."

    parts = [header]
    if changes:
        parts.append(f"\n\n{changes}")

    return "".join(parts)


class EditPatchModal(ui.Modal):
    """Modal pour éditer le texte du patch note (FR ou EN)."""

    def __init__(self, texts: dict, is_english: bool, view: PatchNoteView) -> None:
        title = (
            "Éditer Patch Note (Anglais)"
            if is_english
            else "Éditer Patch Note (Français)"
        )
        super().__init__(title=title)
        self.texts = texts
        self.is_english = is_english
        self.view_ref = view

        self.changes_input = ui.TextInput(
            label="Changements",
            default=texts.get("changes", ""),
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=2000,
        )

        self.add_item(self.changes_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        new_texts = {
            "changes": self.changes_input.value,
        }

        if self.is_english:
            self.view_ref.en_texts = new_texts
        else:
            self.view_ref.fr_texts = new_texts

        await self.view_ref.refresh_message(interaction)


class PatchNoteView(ui.View):
    """Vue pour gérer l'envoi du patch note."""

    def __init__(
        self,
        fr_texts: dict,
        en_texts: dict,
        new_version: str,
        files_data: list[tuple[str, bytes]],
        original_interaction: discord.Interaction,
    ) -> None:
        super().__init__(timeout=None)
        self.fr_texts = fr_texts
        self.en_texts = en_texts
        self.new_version = new_version
        self.files_data = files_data
        self.original_interaction = original_interaction

    async def refresh_message(self, interaction: discord.Interaction) -> None:
        """Met à jour le message de test avec les nouvelles données."""
        french_message = _build_message(
            self.fr_texts, self.new_version, is_english=False
        )
        english_message = _build_message(
            self.en_texts, self.new_version, is_english=True
        )
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
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)

        # Update version file
        try:
            with open("data/version.json", "w") as f:
                json.dump({"version": self.new_version}, f, indent=2)
            logging.info(f"Version sauvegardée : {self.new_version}")
        except Exception as e:
            logging.error(f"Erreur sauvegarde version: {e}")
            await interaction.followup.send(
                f"❌ Erreur lors de la sauvegarde de la version: {e}", ephemeral=True
            )
            return

        fr_channel = interaction.guild.get_channel(PARAM.UPDATE_CHANNEL_ID_FR)
        en_channel = interaction.guild.get_channel(PARAM.UPDATE_CHANNEL_ID_EN)

        french_message = _build_message(
            self.fr_texts, self.new_version, is_english=False
        )
        english_message = _build_message(
            self.en_texts, self.new_version, is_english=True
        )

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
            f"✅ Patch **{self.new_version}** déployé !", ephemeral=True
        )

    @ui.button(label="Éditer FR", style=discord.ButtonStyle.blurple)
    async def edit_fr(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        await interaction.response.send_modal(
            EditPatchModal(self.fr_texts, is_english=False, view=self)
        )

    @ui.button(label="Éditer EN", style=discord.ButtonStyle.blurple)
    async def edit_en(
        self, interaction: discord.Interaction, button: ui.Button
    ) -> None:
        await interaction.response.send_modal(
            EditPatchModal(self.en_texts, is_english=True, view=self)
        )

    @ui.button(label="Annuler", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.send_message(
            "❌ Déploiement du patch annulé.", ephemeral=True
        )
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)


class PatchNoteModal(ui.Modal, title="Déployer un Patch"):
    def __init__(self, attachments: list[discord.Attachment]) -> None:
        super().__init__()
        self.attachments = attachments

        # Calculate next version
        self.current_version = "1.0.0"
        self.next_version = "1.0.1"
        try:
            with open("data/version.json") as f:
                data = json.load(f)
                self.current_version = data.get("version", "1.0.0")
                parts = self.current_version.split(".")
                if len(parts) == 3 and all(p.isdigit() for p in parts):
                    self.next_version = f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
        except Exception:
            pass

        self.version_input = ui.TextInput(
            label="Version", default=self.next_version, max_length=20, required=True
        )
        self.message_input = ui.TextInput(
            label="Message du patch (Optionnel)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=2000,
        )

        self.add_item(self.version_input)
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "🚀 Préparation du patch note...", ephemeral=True
        )
        followup = await interaction.original_response()

        new_version = self.version_input.value
        raw_message = self.message_input.value

        await followup.edit(
            content="✨ Traitement du texte (Correction & Traduction)..."
        )

        original_texts = {
            "changes": raw_message,
        }

        corrected_texts = await _correct_french_text(original_texts)
        translated_texts = await _translate_to_english(corrected_texts)

        if raw_message and not translated_texts.get("changes"):
            await followup.edit(
                content="⚠️ La traduction a échoué. Le message anglais sera incomplet."
            )
            await asyncio.sleep(2)

        # Read files into memory
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

        french_message = _build_message(corrected_texts, new_version, is_english=False)
        english_message = _build_message(translated_texts, new_version, is_english=True)
        full_test_message = f"{french_message}\n\n---\n\n{english_message}"

        await followup.edit(content="📤 Envoi de la prévisualisation...")

        test_channel = interaction.guild.get_channel(PARAM.UPDATE_CHANNEL_ID_TEST)

        if not test_channel:
            await followup.edit(content="❌ Canal de test introuvable.")
            return

        view = PatchNoteView(
            corrected_texts, translated_texts, new_version, files_data, interaction
        )

        chunks = _split_message(full_test_message)

        for i, chunk in enumerate(chunks):
            is_last = i == len(chunks) - 1
            current_view = view if is_last else None
            current_files = files_objects if is_last else None

            await test_channel.send(
                content=chunk, files=current_files, view=current_view
            )

        await followup.edit(content="🎉 Prévisualisation envoyée dans le canal test !")


class PatchNoteCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="patch-note",
        description="[🤖 Dev] Déploie un patch et incrémente la version.",
    )
    @app_commands.describe(image="Image optionnelle à joindre.")
    @is_owner()
    async def patch_note(
        self, interaction: discord.Interaction, image: discord.Attachment | None = None
    ) -> None:
        files = [image] if image else []
        await interaction.response.send_modal(PatchNoteModal(files))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PatchNoteCog(bot))
