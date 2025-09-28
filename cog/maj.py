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
from typing import Optional

# Configurez le logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
            await interaction.response.send_message("Vous n'êtes pas autorisé à utiliser cette commande.", ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

async def _ghost_ping(channel: discord.TextChannel):
    """Envoie une mention de rôle supprimée rapidement."""
    if not channel:
        return
    try:
        mention = await channel.send(f"<@&{PARAM.UPDATE_ROLE_ID}>")
        await asyncio.sleep(1)
        await mention.delete()
    except Exception as e:
        logging.error(f"Erreur lors du ghost ping dans {channel.name}: {e}")

async def _send_and_publish(channel: discord.TextChannel, content: str, files: Optional[list[discord.File]] = None, followup_message: Optional[discord.WebhookMessage] = None):
    """Envoie un message, le publie si nécessaire, et ajoute une réaction."""
    if not channel:
        logging.error("Tentative d'envoi à un canal non valide.")
        if followup_message:
            await followup_message.edit(content=f"❌ Erreur: Le canal est introuvable.")
        return

    try:
        if len(content) > 2000:
            logging.warning("Le contenu du message dépasse 2000 caractères et sera tronqué.")
            content = content[:2000]

        msg = await channel.send(content=content, files=files)
        
        if channel.is_news():
            try:
                await msg.publish()
                logging.info(f"Message publié dans le canal d'annonces {channel.name}.")
            except discord.Forbidden:
                logging.error(f"Permissions insuffisantes pour publier dans {channel.name}.")
            except Exception as e:
                logging.error(f"Erreur lors de la publication dans {channel.name}: {e}")

        try:
            verify_emoji = discord.PartialEmoji(name="verify", animated=True, id=1350435235015426130)
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
            await followup_message.edit(content=f"❌ Une erreur est survenue lors de l'envoi du message.")

# --- Translation and Correction --- 

async def _call_gemini_api(prompt: str, schema: dict, api_url: str) -> Optional[dict]:
    """Appelle l'API Gemini avec une nouvelle tentative en cas d'échec."""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema
        }
    }
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = await asyncio.to_thread(
                lambda: requests.post(api_url, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
            )
            response.raise_for_status()
            result = response.json()
            if result.get("candidates") and result["candidates"][0].get("content") and result["candidates"][0]["content"].get("parts"):
                json_str = result["candidates"][0]["content"]["parts"][0]["text"]

                # Extrait le JSON même s'il est enrobé dans du Markdown
                try:
                    json_start = json_str.index('{')
                    json_end = json_str.rindex('}') + 1
                    json_str = json_str[json_start:json_end]
                    return json.loads(json_str)
                except (ValueError, json.JSONDecodeError) as e:
                    logging.error(f"Error parsing JSON from Gemini: {e}\nResponse received: {json_str}")
                    return None
            else:
                logging.warning("Structure de réponse de l'API Gemini inattendue.")
                return None
        except requests.exceptions.RequestException as e:
            logging.error(f"Erreur API Gemini (tentative {attempt + 1}/{max_retries}): {e}")
            await asyncio.sleep(2 ** attempt)
        except json.JSONDecodeError as e:
            logging.error(f"Erreur de décodage JSON de la réponse Gemini: {e}")
            return None
        except Exception as e:
            logging.error(f"Erreur inattendue lors de l'appel à l'API Gemini: {e}", exc_info=True)
            return None
    logging.error(f"Échec de l'appel à l'API Gemini après {max_retries} tentatives.")
    return None

async def _correct_french_text(text_parts: dict, api_url: str) -> dict:
    """Corrige le texte français en utilisant l'API Gemini."""
    prompt = (
        "Corrigez les fautes d'orthographe et de grammaire dans le texte français suivant. "
        "Répondez uniquement avec un objet JSON. L'objet JSON doit avoir quatre clés: 'corrected_title', 'corrected_changes', 'corrected_intro', et 'corrected_outro'. "
        "Préservez tous les sauts de ligne originaux (\n) et les caractères spéciaux comme &; ~; £.\n\n" 
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
            "corrected_outro": {"type": "STRING"}
        },
        "required": ["corrected_title", "corrected_changes", "corrected_intro", "corrected_outro"]
    }
    corrected_data = await _call_gemini_api(prompt, schema, api_url)
    if corrected_data:
        logging.info("Correction française réussie.")
        return {
            'title': corrected_data.get("corrected_title", text_parts['title']),
            'changes': corrected_data.get("corrected_changes", text_parts['changes']).replace('\\n', '\n'),
            'intro': corrected_data.get("corrected_intro", text_parts['intro']),
            'outro': corrected_data.get("corrected_outro", text_parts['outro'])
        }
    logging.warning("Échec de la correction, utilisation du texte original.")
    return text_parts

async def _translate_to_english(text_parts: dict, api_url: str) -> dict:
    """Traduit le texte en anglais en utilisant l'API Gemini."""
    prompt = (
        "Traduisez le texte suivant du français à l'anglais. Répondez uniquement avec un objet JSON. "
        "L'objet JSON doit avoir quatre clés: 'title', 'changes', 'intro', et 'outro'. "
        "Préservez les sauts de ligne (\n). Ne traduisez pas les mots entre `...` ni les emojis Discord (<:...:...>).\n\n" 
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
            "outro": {"type": "STRING"}
        },
        "required": ["title", "changes", "intro", "outro"]
    }
    translated_data = await _call_gemini_api(prompt, schema, api_url)
    if translated_data:
        logging.info("Traduction anglaise réussie.")
        return {
            'title': translated_data.get("title", ""),
            'changes': translated_data.get("changes", "").replace('\\n', '\n'),
            'intro': translated_data.get("intro", ""),
            'outro': translated_data.get("outro", "")
        }
    logging.error("Échec de la traduction.")
    return {'title': "", 'changes': "", 'intro': "", 'outro': ""}


class UpdateModal(ui.Modal, title='Nouvelle Mise à Jour'):
    """Modal Discord pour collecter les informations d'une nouvelle mise à jour."""
    def __init__(self, attachments: list[discord.Attachment], is_test_run: bool):
        super().__init__()
        self.attachments = attachments
        self.is_test_run = is_test_run
        self.api_url_gemini = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={gemini_api_key}"
        try:
            with open('version.json', 'r') as f:
                self.version_number.default = json.load(f).get('version', '1.0.0')
        except (FileNotFoundError, json.JSONDecodeError):
            self.version_number.default = '1.0.0'

    update_name = ui.TextInput(label='Nom de la Mise à Jour (ex: v1.2.3)', max_length=100, required=True)
    version_number = ui.TextInput(label='Numéro de version (ex: 1.0.1)', max_length=20, required=True)
    intro_message = ui.TextInput(label='Message d\'introduction (facultatif)', max_length=500, required=False)
    changes = ui.TextInput(label='Qu\'est-ce qui a changé ? &:✅ / ~:❌ / £:⏳', style=discord.TextStyle.paragraph, max_length=2000, required=True)
    outro_message = ui.TextInput(label='Message de conclusion (facultatif)', max_length=500, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        """Gère la soumission du modal."""
        await interaction.response.send_message("🚀 Préparation de l'annonce...", ephemeral=True)
        followup_message = await interaction.original_response()

        self._save_version()

        await followup_message.edit(content="✨ Correction et traduction du contenu...")
        
        original_texts = {
            'title': self.update_name.value,
            'changes': self.changes.value,
            'intro': self.intro_message.value or "",
            'outro': self.outro_message.value or ""
        }

        corrected_texts = await _correct_french_text(original_texts, self.api_url_gemini)
        translated_texts = await _translate_to_english(corrected_texts, self.api_url_gemini)

        french_message = self._build_message(corrected_texts, is_english=False)
        english_message = self._build_message(translated_texts, is_english=True)

        if not translated_texts.get('title') or not translated_texts.get('changes'):
            english_message = f"### {PARAM.crossmarck} Translation failed\n\n"
            await followup_message.edit(content="⚠️ La traduction a échoué. Le message anglais sera incomplet.")
            await asyncio.sleep(2)

        attachment_files = await self._prepare_attachments(followup_message)

        await followup_message.edit(content="📤 Envoi de l'annonce sur Discord...")
        
        if self.is_test_run:
            test_channel = interaction.guild.get_channel(PARAM.UPDATE_CHANNEL_ID_TEST)
            full_test_message = f"{french_message}\n\n---\n\n{english_message}"
            await _send_and_publish(test_channel, full_test_message, attachment_files, followup_message)
            await _ghost_ping(test_channel)
        else:
            fr_channel = interaction.guild.get_channel(PARAM.UPDATE_CHANNEL_ID_FR)
            en_channel = interaction.guild.get_channel(PARAM.UPDATE_CHANNEL_ID_EN)
            
            await _send_and_publish(fr_channel, french_message, attachment_files, followup_message)
            await _ghost_ping(fr_channel)
            
            # On ne re-upload pas les fichiers pour le 2ème message
            await _send_and_publish(en_channel, english_message, None, followup_message)
            await _ghost_ping(en_channel)

        await followup_message.edit(content="🎉 Annonce envoyée avec succès !")

    def _save_version(self):
        try:
            with open('version.json', 'w') as f:
                json.dump({'version': self.version_number.value}, f, indent=2)
            logging.info(f"Version mise à jour vers : {self.version_number.value}")
        except (IOError, OSError) as e:
            logging.error(f"Impossible de sauvegarder la version : {e}")

    def _build_message(self, texts: dict, is_english: bool) -> str:
        """Construit le contenu du message de mise à jour."""
        title, intro, changes, outro = texts['title'], texts['intro'], texts['changes'], texts['outro']
        
        if is_english:
            changes = changes.replace('&', PARAM.checkmark).replace('~', PARAM.crossmarck).replace('£', PARAM.in_progress)
            greeting = "👋 Hello to the entire community!\n\n"
            user_update_msg = f"{PARAM.test} <@{PARAM.BOT_ID}> received an update !\n\n"
            conclusion_text = "Stay tuned for future announcements and thank you for your continued support!"
            team_signature = "The Development Team."
            feedback_prompt = f"Use /feedback to report any mistakes or bugs or go to <#1350399062418915418>."
        else:
            changes = changes.replace('&', f"{PARAM.checkmark}:").replace('~', f"{PARAM.crossmarck}:").replace('£', f"{PARAM.in_progress}:")
            greeting = "👋 Coucou à toute la communauté !\n\n"
            user_update_msg = f"{PARAM.test} <@{PARAM.BOT_ID}> a reçu une mise à jour !\n\n"
            conclusion_text = "Restez connectés pour de futures annonces et merci pour votre soutien continu !"
            team_signature = "L\'équipe de développement."
            feedback_prompt = f"Utilisez /feedback pour signaler des erreurs ou des bugs ou allez dans <#1350399062418915418>."

        parts = [f"# {PARAM.annonce} {title} {PARAM.annonce}\n\n", greeting]
        if intro: parts.append(f"{intro}\n\n")
        parts.extend([user_update_msg, f"{changes}\n\n"])
        if outro: parts.append(f"{outro}\n\n")
        parts.append(f"🚀 {conclusion_text} **{feedback_prompt}**\n{team_signature}")
        return "".join(parts)

    async def _prepare_attachments(self, followup_message: discord.WebhookMessage) -> list[discord.File]:
        """Prépare les pièces jointes pour l'envoi."""
        files = []
        for attachment in self.attachments:
            try:
                files.append(discord.File(io.BytesIO(await attachment.read()), filename=attachment.filename))
            except Exception as e:
                logging.error(f"Impossible de lire la pièce jointe {attachment.filename}: {e}")
                await followup_message.edit(content=f"⚠️ Impossible d'attacher le fichier `{attachment.filename}`.")
        return files

class ManagementCog(commands.Cog):
    """Cog pour les commandes de gestion du bot."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="update", description="[🤖 Dev] Envoie une annonce de mise à jour.")
    @app_commands.describe(attachments="Fichier à joindre.", test="Envoyer sur le canal de test ?")
    @app_commands.choices(test=[app_commands.Choice(name="Oui", value="oui"), app_commands.Choice(name="Non", value="non")])
    @is_owner()
    async def update_command(self, interaction: discord.Interaction, test: str, attachments: Optional[discord.Attachment] = None):
        files = [attachments] if attachments else []
        await interaction.response.send_modal(UpdateModal(attachments=files, is_test_run=(test == "oui")))

    @app_commands.command(name="patch-note", description="[🤖 Dev] Déploie un patch et incrémente la version.")
    @is_owner()
    async def patch_note_command(self, interaction: discord.Interaction):
        """Annonce un patch, incrémente la version et notifie les canaux."""
        await interaction.response.defer(ephemeral=True)
        try:
            with open('version.json', 'r+') as f:
                data = json.load(f)
                current_version = data.get('version', '1.0.0')
                
                parts = current_version.split('.')
                if len(parts) != 3 or not all(p.isdigit() for p in parts):
                    await interaction.followup.send(f"❌ Format de version invalide: `{current_version}`.", ephemeral=True)
                    return

                new_version = f"{parts[0]}.{parts[1]}.{int(parts[2]) + 1}"
                data['version'] = new_version
                
                f.seek(0)
                json.dump(data, f, indent=2)
                f.truncate()
            logging.info(f"Version incrémentée à {new_version}")

        except FileNotFoundError:
            await interaction.followup.send("❌ `version.json` introuvable. Utilisez `/update` d'abord.", ephemeral=True)
            return
        except (json.JSONDecodeError, KeyError) as e:
            await interaction.followup.send(f"❌ Erreur de lecture de `version.json`: {e}", ephemeral=True)
            return

        fr_channel = self.bot.get_channel(PARAM.UPDATE_CHANNEL_ID_FR)
        en_channel = self.bot.get_channel(PARAM.UPDATE_CHANNEL_ID_EN)

        message_fr = f"**⚙️ Patch Déployé !**\n\nUn nouveau patch vient d'être appliqué. La version est maintenant la **{new_version}**."
        message_en = f"**⚙️ Patch Deployed!**\n\nA new patch has just been applied. The version is now **{new_version}**."

        await _send_and_publish(fr_channel, message_fr)
        await _ghost_ping(fr_channel)
        await _send_and_publish(en_channel, message_en)
        await _ghost_ping(en_channel)

        await interaction.followup.send(f"✅ Patch **{new_version}** annoncé.", ephemeral=True)

    @update_command.error
    async def update_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Gestionnaire d'erreurs pour la commande /update."""
        message = f"Une erreur est survenue: {error}"
        if isinstance(error, app_commands.CheckFailure):
            return # Déjà géré par le check
        elif isinstance(error, app_commands.CommandOnCooldown):
            message = f"Commande en cooldown. Réessayez dans {error.retry_after:.1f}s."
        else:
            logging.error(f"Erreur inattendue dans /update: {error}", exc_info=True)

        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(ManagementCog(bot))