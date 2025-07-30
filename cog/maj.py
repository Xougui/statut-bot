import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import asyncio
import requests # Importe requests ici
import io       # Importe io ici

# --- Configuration du canal de mise à jour ---
# Remplacez ceci par l'ID du canal où les annonces de mise à jour seront envoyées.
# C'est un exemple, vous devriez le configurer dans un fichier de configuration ou des variables d'environnement.
UPDATE_CHANNEL_ID = 1388563238559420417 # Remplacez par l'ID réel de votre canal

# Importe les variables de configuration depuis le fichier PARAM.py
# ASSUREZ-VOUS D'AVOIR UN FICHIER 'PARAM.py' dans le même répertoire que votre bot
# ou un chemin accessible, et que ce fichier contient une variable 'owners', par exemple :
# # PARAM.py
# owners = {1234567890123456789, 9876543210987654321}
import PARAM

# --- Modal pour la saisie des informations de mise à jour ---
class UpdateModal(ui.Modal, title='Nouvelle Mise à Jour'):
    """
    Modal Discord pour collecter les informations d'une nouvelle mise à jour.
    """
    def __init__(self, attachments: list[discord.Attachment]):
        super().__init__()
        self.attachments = attachments # Stocke les pièces jointes passées par la commande
        self.update_channel_id = UPDATE_CHANNEL_ID # Récupère l'ID du canal cible

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
        """
        Gère la soumission du modal par l'utilisateur.
        Formate le message, le traduit et l'envoie au canal spécifié.
        """
        await interaction.response.defer(thinking=True) # Affiche "Le bot réfléchit..."

        update_title_fr = self.update_name.value
        changes_fr = self.changes.value

        # --- Formatage du message en français ---
        french_message_content = f"📣 **GROSSE ANNONCE !** 📣\n\n" \
                                 f"Salut tout le monde !\n\n" \
                                 f"Nous avons une nouvelle mise à jour : **{update_title_fr}**\n\n" \
                                 f"Voici ce qui a changé :\n{changes_fr}\n\n" \
                                 f"Restez connectés pour les prochaines nouveautés !"

        # --- Traduction du message en anglais via l'API Gemini ---
        english_message_content = ""
        try:
            # Préparation du prompt pour la traduction
            prompt = f"Traduisez le texte suivant du français à l'anglais. Ne répondez qu'avec la traduction.\n\n" \
                     f"Titre: {update_title_fr}\n" \
                     f"Changements: {changes_fr}"

            chatHistory = []
            chatHistory.append({ "role": "user", "parts": [{ "text": prompt }] })
            payload = { "contents": chatHistory }
            apiKey = "" # Laissez vide, l'API key sera fournie par l'environnement Canvas
            apiUrl = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={apiKey}"

            # Implémentation de l'exponentielle backoff pour les appels API
            retries = 0
            max_retries = 5
            while retries < max_retries:
                try:
                    response = await asyncio.to_thread(
                        lambda: requests.post(apiUrl, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
                    )
                    response.raise_for_status() # Lève une exception pour les codes d'erreur HTTP
                    result = response.json()

                    if result.get("candidates") and result["candidates"][0].get("content") and result["candidates"][0]["content"].get("parts"):
                        translated_text = result["candidates"][0]["content"]["parts"][0]["text"]
                        # Le modèle peut renvoyer le titre et les changements séparément,
                        # nous devons les extraire et les formater.
                        # Une approche simple est de rechercher les lignes "Title:" et "Changes:".
                        lines = translated_text.split('\n')
                        translated_title = ""
                        translated_changes = ""
                        for line in lines:
                            if line.startswith("Title:"):
                                translated_title = line.replace("Title:", "").strip()
                            elif line.startswith("Changes:"):
                                translated_changes = line.replace("Changes:", "").strip()
                        
                        if translated_title and translated_changes:
                            english_message_content = f"📣 **BIG ANNOUNCEMENT!** 📣\n\n" \
                                                      f"Hello everyone!\n\n" \
                                                      f"We have a new update: **{translated_title}**\n\n" \
                                                      f"Here's what changed:\n{translated_changes}\n\n" \
                                                      f"Stay tuned for future updates!"
                        else:
                            # Si le formatage n'est pas celui attendu, utilisez la traduction brute
                            english_message_content = f"📣 **BIG ANNOUNCEMENT!** 📣\n\n" \
                                                      f"Hello everyone!\n\n" \
                                                      f"We have a new update: **{update_title_fr}**\n\n" \
                                                      f"Here's what changed:\n{translated_text}\n\n" \
                                                      f"Stay tuned for future updates!"
                        break # Sortir de la boucle de relecture si la traduction est réussie
                    else:
                        print("Erreur: La structure de la réponse de l'API Gemini est inattendue.")
                        english_message_content = f"Could not translate. Original changes:\n{changes_fr}"
                        break
                except requests.exceptions.RequestException as e:
                    print(f"Erreur lors de l'appel à l'API Gemini (tentative {retries + 1}/{max_retries}): {e}")
                    retries += 1
                    await asyncio.sleep(2 ** retries) # Attente exponentielle
                except json.JSONDecodeError as e:
                    print(f"Erreur de décodage JSON de la réponse Gemini: {e}")
                    english_message_content = f"Could not translate due to API response error. Original changes:\n{changes_fr}"
                    break
        except Exception as e:
            print(f"Une erreur inattendue est survenue lors de la traduction: {e}")
            english_message_content = f"Could not translate due to an unexpected error. Original changes:\n{changes_fr}"

        # --- Récupération du canal et envoi du message ---
        target_channel = interaction.guild.get_channel(self.update_channel_id)
        if not target_channel:
            await interaction.followup.send(
                f"Erreur: Le canal avec l'ID `{self.update_channel_id}` n'a pas été trouvé. "
                "Veuillez vérifier l'ID configuré.", ephemeral=True
            )
            return

        # Création de l'embed pour un meilleur affichage
        embed_fr = discord.Embed(
            title=f"Mise à Jour : {update_title_fr}",
            description=french_message_content,
            color=discord.Color.blue()
        )
        embed_fr.set_footer(text="Version française")

        embed_en = discord.Embed(
            title=f"Update : {translated_title if translated_title else update_title_fr}", # Utilise le titre traduit si disponible
            description=english_message_content,
            color=discord.Color.green()
        )
        embed_en.set_footer(text="English version")

        # Préparation des fichiers à envoyer
        files_to_send = []
        for attachment in self.attachments:
            try:
                # Télécharge le fichier en mémoire
                file_bytes = await attachment.read()
                files_to_send.append(discord.File(fp=io.BytesIO(file_bytes), filename=attachment.filename))
            except Exception as e:
                print(f"Impossible de télécharger la pièce jointe {attachment.filename}: {e}")
                await interaction.followup.send(f"Avertissement: Impossible d'attacher le fichier `{attachment.filename}`.", ephemeral=True)

        try:
            # Envoi des embeds et des fichiers
            await target_channel.send(embeds=[embed_fr, embed_en], files=files_to_send)
            await interaction.followup.send("L'annonce de mise à jour a été envoyée avec succès !", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send(
                "Je n'ai pas la permission d'envoyer des messages dans ce canal. "
                "Veuillez vérifier mes permissions.", ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"Une erreur est survenue lors de l'envoi du message : {e}", ephemeral=True)


# --- Cog principal ---
class ManagementCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Vérification personnalisée pour les propriétaires
    def is_owner():
        async def predicate(interaction: discord.Interaction):
            # Assurez-vous que PARAM.owners est un ensemble ou une liste d'IDs
            if interaction.user.id not in PARAM.owners:
                await interaction.response.send_message("Vous n'êtes pas autorisé à utiliser cette commande.", ephemeral=True)
                return False
            return True
        return app_commands.check(predicate)

    @app_commands.command(name="update", description="[🤖 Dev ] Envoie une annonce de mise à jour du bot.")
    @app_commands.describe(
        attachments="Fichier à joindre à l'annonce (image, document, etc.)" # Description ajustée pour une seule pièce jointe
    )
    @is_owner() # Applique la vérification des propriétaires
    async def update_command(self, interaction: discord.Interaction, attachments: discord.Attachment = None):
        """
        Commande slash pour initier le processus de mise à jour.
        Ouvre un modal pour la saisie des détails de la mise à jour.
        """
        files_for_modal = []
        if attachments:
            files_for_modal.append(attachments)

        modal = UpdateModal(attachments=files_for_modal)
        await interaction.response.send_modal(modal)

    @update_command.error
    async def update_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """
        Gère les erreurs spécifiques à la commande /update.
        """
        if isinstance(error, app_commands.CheckFailure):
            # Le message d'erreur est déjà envoyé par la fonction is_owner()
            pass
        elif isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Cette commande est en cooldown. Veuillez réessayer dans {error.retry_after:.1f} secondes.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"Une erreur inattendue est survenue lors de l'exécution de la commande : {error}",
                ephemeral=True
            )
            print(f"Erreur inattendue dans /update: {error}")

# La fonction setup_hook et la création du bot sont supprimées d'ici.
# Elles doivent être gérées par le fichier principal (main.py).

# --- Fonction de configuration du cog ---
async def setup(bot: commands.Bot):
    """
    Fonction appelée par Discord.py pour ajouter le cog au bot.
    """
    await bot.add_cog(ManagementCog(bot))
    print("ManagementCog chargé.") # Ajout d'un message pour confirmer le chargement
