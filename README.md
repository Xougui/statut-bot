# Status Bot - Surveillez le statut de votre bot Discord !

Ce bot Discord est conçu pour vous aider à savoir si un autre bot sur votre serveur est **en ligne** ou **hors ligne**. Il fait ça en mettant à jour automatiquement le nom d'un salon Discord et un message spécial pour que vous voyiez en temps réel si votre bot cible fonctionne bien.

---

## 📋 Ce dont vous avez besoin avant de commencer (Prérequis)

Avant de plonger dans le code, assurez-vous d'avoir ces éléments :

1.  **Python 3.8 ou plus récent** : C'est le langage de programmation utilisé. Si vous ne l'avez pas, téléchargez-le depuis le site officiel de Python.
    * [Télécharger Python](https://www.python.org/downloads/)

2.  **Un compte Discord et un serveur** : Vous devez avoir un compte Discord et un serveur où vous avez les permissions d'administrateur (pour créer des salons, des rôles, etc.).

3.  **Un Bot Discord pour le "Status Bot"** : C'est le bot que vous allez faire fonctionner pour surveiller l'autre.
    * Si vous n'en avez pas, créez-en un sur le [Portail des Développeurs Discord](https://discord.com/developers/applications).
    * **Étapes importantes pour votre Status Bot :**
        1.  Allez dans la section "Bot" de votre application, puis cliquez sur "Add Bot".
        2.  **TRÈS IMPORTANT** : Activez les "Privileged Gateway Intents" (`PRESENCE INTENT` et `SERVER MEMBERS INTENT`). C'est obligatoire pour que votre bot puisse voir le statut des autres membres et bots.
        3.  Récupérez le **token** de votre bot (c'est une longue chaîne de caractères). Gardez-le secret et ne le partagez jamais !

4.  **Activer le Mode Développeur sur Discord** : Cela vous permettra de copier facilement les identifiants (IDs) des salons, messages, utilisateurs et rôles.
    * Allez dans `Paramètres utilisateur` > `Avancés`.
    * Activez l'option `Mode Développeur`.
    * Maintenant, en faisant un clic droit sur un élément Discord (utilisateur, salon, message, rôle), vous pourrez "Copier l'ID".

---

## ⚙️ Comment installer le bot (Installation)

Suivez ces étapes pour préparer le bot sur votre ordinateur :

1.  **Téléchargez les fichiers du bot** : Si vous avez reçu les fichiers, mettez-les dans un dossier sur votre ordinateur. Si c'est un dépôt GitHub, vous pouvez le "cloner" ou télécharger le fichier ZIP.

2.  **Ouvrez le Terminal ou l'Invite de Commandes** :
    * Sur Windows : Cherchez "cmd" ou "PowerShell" dans le menu Démarrer.
    * Sur macOS/Linux : Cherchez "Terminal".
    * Naviguez jusqu'au dossier où vous avez mis les fichiers du bot. Par exemple, si votre dossier est `C:\Users\VotreNom\Documents\StatusBot`, tapez `cd C:\Users\VotreNom\Documents\StatusBot` et appuyez sur Entrée.

3.  **Installez les dépendances** : Ce sont des "modules" supplémentaires dont Python a besoin pour que le bot fonctionne. Dans votre Terminal/Invite de Commandes, tapez cette commande et appuyez sur Entrée :
    ```bash
    pip install -r requirements.txt
    ```
    Attendez que l'installation se termine. Si vous voyez des messages d'erreur, assurez-vous que Python est bien installé et que vous êtes dans le bon dossier.

---

## 🛠️ Comment configurer le bot (Configuration)

La configuration se fait dans 3 fichiers principaux. Soyez très attentif !

### 1. Le fichier `.env` (Très important pour votre token !)

Ce fichier est spécial car il contient le "token" secret de votre bot. Il ne doit jamais être partagé.

1.  À la racine de votre dossier de bot (là où se trouve `main.py`), créez un nouveau fichier.
2.  Nommez-le exactement `.env` (le point au début est important !).
3.  Ouvrez ce fichier avec un éditeur de texte simple (comme le Bloc-notes sur Windows, TextEdit sur Mac, ou VS Code).
4.  Ajoutez la ligne suivante à l'intérieur, en remplaçant `VOTRE_TOKEN_DE_BOT_ICI` par le vrai token que vous avez copié depuis le Portail des Développeurs Discord :

    ```
    token=VOTRE_TOKEN_DE_BOT_ICI
    ```

### 2. Le fichier `PARAM.py`

Ce fichier contient tous les paramètres importants pour le bot. Ouvrez `PARAM.py` avec un éditeur de texte et modifiez les valeurs suivantes :

```python
# --- PROPRIÉTAIRES DU BOT ---
# Mettez ici les IDs des utilisateurs qui auront les permissions de propriétaire sur le bot.
# Pour obtenir votre ID : activez le mode développeur sur Discord, faites un clic droit sur votre profil et "Copier l'ID".
owners = [946098490654740580, 1178647820052467823] # Remplacez par vos IDs !

# --- COULEUR DES EMBEDS ---
# Couleur par défaut pour les messages intégrés (embeds). Utilisez un format hexadécimal (ex: 0xd7a826).
couleur = 0xd7a826

# --- ID DU BOT À SURVEILLER ---
# L'ID de l'utilisateur du bot DONT vous voulez suivre le statut.
# Pour obtenir son ID : activez le mode développeur, faites un clic droit sur le profil du bot cible et "Copier l'ID".
BOT_ID = 1335228717403996160 # Remplacez par l'ID du bot à surveiller !

# --- IDs DES CANAUX ET MESSAGES ---
# L'ID du salon textuel dont le nom sera modifié (ex: 🟢・online ou 🔴・offline).
# Pour obtenir son ID : activez le mode développeur, faites un clic droit sur le salon et "Copier l'ID du salon".
CHANNEL_ID = 1345710620200407123 # Remplacez par l'ID de votre salon de statut !

# L'ID du message qui sera édité pour afficher le statut détaillé dans le CHANNEL_ID.
# Pour l'obtenir :
#   1. Allez dans le salon que vous avez défini pour CHANNEL_ID.
#   2. Envoyez un message temporaire (par exemple, "Ceci est le message de statut").
#   3. Faites un clic droit sur CE message et "Copier l'ID du message".
#   4. Collez l'ID ici.
MESSAGE_ID = 1346867347255721984 # Remplacez par l'ID de votre message de statut !

# L'ID du salon où les logs (changements de statut) seront envoyés (sans mention).
# Pour obtenir son ID : activez le mode développeur, faites un clic droit sur le salon et "Copier l'ID du salon".
LOGS_CHANNEL_ID = 1350443541867790406 # Remplacez par l'ID de votre salon de logs !

# L'ID du rôle à mentionner dans les messages de statut envoyés dans CHANNEL_ID.
# Pour obtenir l'ID d'un rôle : Allez dans les Paramètres du serveur > Rôles. Faites un clic droit sur le rôle désiré et "Copier l'ID du rôle".
ROLE_ID = 1350429004032770068 # Remplacez par l'ID du rôle à pinger !
```

### 3. Le fichier `cog/statut.py` (Modification du Ping)

Lorsque le bot surveillé passe hors ligne, le Status Bot envoie une notification (un "ping") à un rôle. Vous devez configurer quel rôle sera notifié.

1.  Ouvrez le fichier `cog/statut.py` (il est dans le dossier `cog`).
2.  Allez à la **ligne 130** (environ). Vous y trouverez une ligne qui ressemble à ceci :

    ```python
    ping = await channel.send(content="<@&1350429004032770068>")
    ```

3.  Remplacez `1350429004032770068` par l'ID du rôle que vous souhaitez notifier.
    * **Pour obtenir l'ID d'un rôle** :
        1. Allez dans les `Paramètres du serveur` > `Rôles` sur Discord.
        2. Faites un clic droit sur le rôle désiré et `Copier l'ID du rôle`.

---

## 🚀 Lancement du Bot

Une fois que tous les fichiers sont configurés avec les bons IDs :

1.  **Invitez votre Status Bot** sur votre serveur Discord. Assurez-vous qu'il a les permissions nécessaires :
    * Voir les salons
    * Envoyer des messages
    * Gérer les messages (pour éditer le message de statut)
    * Gérer le salon (pour changer son nom)
2.  **Invitez le bot à surveiller** (celui dont vous voulez connaître le statut) sur le même serveur. Le Status Bot ne peut pas voir son statut s'ils ne sont pas sur un serveur commun.
3.  Ouvrez un terminal ou une invite de commandes dans le dossier où se trouve `main.py` et lancez le bot avec la commande :
    ```bash
    python main.py
    ```

Le bot devrait se connecter et commencer à surveiller votre bot cible ! Laissez cette fenêtre de terminal ouverte pour que le bot reste en ligne.

---

## 🤖 Commandes du Bot

Voici les commandes que vous pouvez utiliser avec le Status Bot :

* `s%s <on|off>` : (Pour les propriétaires du bot seulement) Cette commande vous permet de forcer manuellement le statut affiché du bot cible à "en ligne" (`on`) ou "hors ligne" (`off`). Utile pour tester ou corriger un affichage.
    * Exemple : `s%s on`
* `/ping-infos` : Cette commande affiche des informations techniques et des statistiques détaillées sur le Status Bot lui-même (latence, utilisation mémoire, etc.).