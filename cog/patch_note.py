import asyncio
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
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Récupération de la clé API Gemini depuis les variables d'environnement
gemini_api_key = os.getenv("GEMINI_API")

# Client instance
client = genai.Client(api_key=gemini_api_key)


# --- Helpers (Duplicated from cog/maj.py to remain self-contained) ---

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
        for i, chunk in enumerate(chunks):
            current_files = files if i == len(chunks) - 1 else None
            msg = await channel.send(content=chunk, files=current_files)

            if channel.is_news():
                try:
                    await msg.publish()
                    logging.info(f"Message publié dans le canal d'annonces {channel.name}.")
                except discord.Forbidden:
                    logging.error(f"Permissions insuffisantes pour publier dans {channel.name}.")
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
        logging.error(f"Permissions insuffisantes pour envoyer des messages dans {channel.name}.")
        if followup_message:
            await followup_message.edit(content=f"❌ Erreur: Permissions insuffisantes pour le canal {channel.name}.")
    except Exception as e:
        logging.error(f"Erreur inattendue lors de l'envoi dans {channel.name}: {e}", exc_info=True)
        if followup_message:
            await followup_message.edit(content="❌ Une erreur est survenue lors de l'envoi du message.")


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
                    logging.error(f"Error parsing JSON from Gemini: {e}\nResponse received: {response.text}")
                    return None
            else:
                logging.warning("Structure de réponse de l'API Gemini inattendue.")
                return None
        except Exception as e:
            logging.error(f"Erreur API Gemini (tentative {attempt + 1}/{max_retries}): {e}")
            await asyncio.sleep(2**attempt)
    logging.error(f"Échec de l'appel à l'API Gemini après {max_retries} tentatives.")
    return None


async def _process_patch_text(text: str) -> tuple[str, str]:
    """Corrects French text and translates to English using Gemini."""
    if not text:
        return "", ""

    # Correct French
    prompt_fr = (
        "Agis comme un correcteur orthographique et grammatical expert. Corrige le texte français suivant.\n"
        "Règles strictes :\n"
        "1. Réponds uniquement avec un objet JSON valide contenant la clé 'corrected_text'.\n"
        "2. PRÉSERVE scrupuleusement les emojis et la mise en forme.\n\n"
        f"Texte: {text}"
    )
    schema_fr = {
        "type": "OBJECT",
        "properties": {"corrected_text": {"type": "STRING"}},
        "required": ["corrected_text"]
    }
    corrected_data = await _call_gemini_api(prompt_fr, schema_fr)
    fr_text = corrected_data.get("corrected_text", text) if corrected_data else text

    # Translate to English
    prompt_en = (
        "Agis comme un traducteur expert du français vers l'anglais. Traduis le texte suivant.\n"
        "Règles strictes :\n"
        "1. Réponds uniquement avec un objet JSON valide contenant la clé 'translated_text'.\n"
        "2. PRÉSERVE scrupuleusement les emojis et la mise en forme.\n\n"
        f"Texte original: {fr_text}"
    )
    schema_en = {
        "type": "OBJECT",
        "properties": {"translated_text": {"type": "STRING"}},
        "required": ["translated_text"]
    }
    translated_data = await _call_gemini_api(prompt_en, schema_en)
    en_text = translated_data.get("translated_text", "") if translated_data else ""

    return fr_text.replace("\\n", "\n"), en_text.replace("\\n", "\n")


class EditPatchModal(ui.Modal):
    """Modal pour éditer le texte du patch note (FR ou EN)."""
    def __init__(self, text: str, is_english: bool, view: "PatchNoteView") -> None:
        title = "Éditer Patch Note (Anglais)" if is_english else "Éditer Patch Note (Français)"
        super().__init__(title=title)
        self.is_english = is_english
        self.view_ref = view

        self.text_input = ui.TextInput(
            label="Message",
            default=text,
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=2000
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if self.is_english:
            self.view_ref.en_message = self.text_input.value
        else:
            self.view_ref.fr_message = self.text_input.value
        await self.view_ref.refresh_message(interaction)


class PatchNoteView(ui.View):
    """Vue pour gérer l'envoi du patch note."""
    def __init__(self, fr_message: str, en_message: str, new_version: str, file_data: tuple[str, bytes] | None, original_interaction: discord.Interaction):
        super().__init__(timeout=None)
        self.fr_message = fr_message
        self.en_message = en_message
        self.new_version = new_version
        self.file_data = file_data
        self.original_interaction = original_interaction

    def _build_final_messages(self) -> tuple[str, str]:
        fr_base = f"**⚙️ Patch Déployé !**\n\nUn nouveau patch vient d'être appliqué. La version est maintenant la **{self.new_version}**."
        en_base = f"**⚙️ Patch Deployed!**\n\nA new patch has just been applied. The version is now **{self.new_version}**."

        fr_final = f"{fr_base}\n\n{self.fr_message}" if self.fr_message else fr_base
        en_final = f"{en_base}\n\n{self.en_message}" if self.en_message else en_base

        return fr_final, en_final

    async def refresh_message(self, interaction: discord.Interaction) -> None:
        fr_text, en_text = self._build_final_messages()
        full_preview = f"{fr_text}\n\n---\n\n{en_text}"

        files = []
        if self.file_data:
            files.append(discord.File(io.BytesIO(self.file_data[1]), filename=self.file_data[0]))

        chunks = _split_message(full_preview)

        if not interaction.response.is_done():
            await interaction.response.defer()

        # Delete old message to handle chunks correctly if size changed
        if interaction.message:
            with contextlib.suppress(discord.HTTPException, discord.Forbidden):
                await interaction.message.delete()

        channel = interaction.channel
        if not channel:
            return

        for i, chunk in enumerate(chunks):
            is_last = i == len(chunks) - 1
            current_view = self if is_last else None
            current_files = files if is_last else None # Re-create file object if needed or use valid one

            # Re-create file object because it is consumed
            if self.file_data and is_last:
                 current_files = [discord.File(io.BytesIO(self.file_data[1]), filename=self.file_data[0])]

            await channel.send(content=chunk, files=current_files, view=current_view)

    @ui.button(label="Envoyer Production", style=discord.ButtonStyle.green)
    async def send_prod(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.defer()
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)

        # Update version file
        try:
            with open("version.json", "w") as f:
                json.dump({"version": self.new_version}, f, indent=2)
            logging.info(f"Version sauvegardée : {self.new_version}")
        except Exception as e:
            logging.error(f"Erreur sauvegarde version: {e}")
            await interaction.followup.send(f"❌ Erreur lors de la sauvegarde de la version: {e}", ephemeral=True)
            return

        fr_channel = interaction.guild.get_channel(PARAM.UPDATE_CHANNEL_ID_FR)
        en_channel = interaction.guild.get_channel(PARAM.UPDATE_CHANNEL_ID_EN)

        fr_text, en_text = self._build_final_messages()

        files_fr = [discord.File(io.BytesIO(self.file_data[1]), filename=self.file_data[0])] if self.file_data else []
        await _send_and_publish(fr_channel, fr_text, files_fr)
        await _ghost_ping(fr_channel)

        files_en = [discord.File(io.BytesIO(self.file_data[1]), filename=self.file_data[0])] if self.file_data else []
        await _send_and_publish(en_channel, en_text, files_en)
        await _ghost_ping(en_channel)

        await interaction.followup.send(f"✅ Patch **{self.new_version}** déployé !", ephemeral=True)

    @ui.button(label="Éditer FR", style=discord.ButtonStyle.blurple)
    async def edit_fr(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.send_modal(EditPatchModal(self.fr_message, False, self))

    @ui.button(label="Éditer EN", style=discord.ButtonStyle.blurple)
    async def edit_en(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.send_modal(EditPatchModal(self.en_message, True, self))

    @ui.button(label="Annuler", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button) -> None:
        await interaction.response.send_message("❌ Déploiement du patch annulé.", ephemeral=True)
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)


class PatchNoteModal(ui.Modal, title="Déployer un Patch"):
    def __init__(self, attachment_data: tuple[str, bytes] | None):
        super().__init__()
        self.attachment_data = attachment_data

        # Calculate next version
        self.current_version = "1.0.0"
        self.next_version = "1.0.1"
        try:
            with open("version.json", "r") as f:
                data = json.load(f)
                self.current_version = data.get("version", "1.0.0")
                parts = self.current_version.split(".")
                if len(parts) == 3 and all(p.isdigit() for p in parts):
                    self.next_version = f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
        except Exception:
            pass

        self.version_input = ui.TextInput(
            label="Version",
            default=self.next_version,
            max_length=20,
            required=True
        )
        self.message_input = ui.TextInput(
            label="Message du patch (Optionnel)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=2000
        )

        self.add_item(self.version_input)
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("🚀 Préparation du patch note...", ephemeral=True)
        followup = await interaction.original_response()

        new_version = self.version_input.value
        raw_message = self.message_input.value

        fr_message = ""
        en_message = ""

        if raw_message:
            await followup.edit(content="✨ Traitement du texte (Correction & Traduction)...")
            fr_message, en_message = await _process_patch_text(raw_message)

        await followup.edit(content="📤 Envoi de la prévisualisation...")

        view = PatchNoteView(fr_message, en_message, new_version, self.attachment_data, interaction)

        # Initial preview
        fr_final = f"**⚙️ Patch Déployé !**\n\nUn nouveau patch vient d'être appliqué. La version est maintenant la **{new_version}**."
        if fr_message:
            fr_final += f"\n\n{fr_message}"

        en_final = f"**⚙️ Patch Deployed!**\n\nA new patch has just been applied. The version is now **{new_version}**."
        if en_message:
            en_final += f"\n\n{en_message}"

        full_preview = f"{fr_final}\n\n---\n\n{en_final}"

        chunks = _split_message(full_preview)
        channel = interaction.guild.get_channel(PARAM.UPDATE_CHANNEL_ID_TEST)

        if not channel:
             await followup.edit(content="❌ Canal de test introuvable.")
             return

        for i, chunk in enumerate(chunks):
            is_last = i == len(chunks) - 1
            current_view = view if is_last else None

            files = []
            if self.attachment_data and is_last:
                 files = [discord.File(io.BytesIO(self.attachment_data[1]), filename=self.attachment_data[0])]

            await channel.send(content=chunk, files=files, view=current_view)

        await followup.edit(content="🎉 Prévisualisation envoyée dans le canal test !")


class PatchNoteCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="patch-note", description="[🤖 Dev] Déploie un patch et incrémente la version.")
    @app_commands.describe(image="Image optionnelle à joindre.")
    @is_owner()
    async def patch_note(self, interaction: discord.Interaction, image: discord.Attachment | None = None) -> None:
        attachment_data = None
        if image:
            try:
                data = await image.read()
                attachment_data = (image.filename, data)
            except Exception as e:
                await interaction.response.send_message(f"❌ Erreur lecture image: {e}", ephemeral=True)
                return

        await interaction.response.send_modal(PatchNoteModal(attachment_data))

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PatchNoteCog(bot))
