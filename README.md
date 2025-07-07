# Status Bot

Ce bot Discord a pour but de surveiller le statut (en ligne/hors ligne) d'un autre bot sur votre serveur. Il met à jour automatiquement le nom d'un salon et un message spécifique pour indiquer en temps réel si le bot cible est fonctionnel.

## 📋 Prérequis

Avant de commencer, assurez-vous d'avoir les éléments suivants :

1.  **Python 3.8 ou supérieur** installé sur votre machine.
2.  Un **compte Discord** et un **serveur** où vous avez les permissions d'administrateur.
3.  Un **Bot Discord**. Si vous n'en avez pas, créez-en un sur le [Portail des Développeurs Discord](https://discord.com/developers/applications).
    - Allez dans la section "Bot" de votre application, cliquez sur "Add Bot".
    - Activez les **"Privileged Gateway Intents"** : `PRESENCE INTENT` et `SERVER MEMBERS INTENT`. C'est **obligatoire** pour que le bot puisse voir le statut des autres membres.
    - Récupérez le **token** de votre bot. Gardez-le précieusement et ne le partagez jamais.
4.  **Activer le Mode Développeur sur Discord**. C'est nécessaire pour obtenir les IDs (identifiants).
    - Allez dans `Paramètres utilisateur` > `Avancés`.
    - Activez l'option `Mode Développeur`.
    - Maintenant, vous pouvez faire un clic droit sur un utilisateur, un salon, un message ou un rôle pour copier son ID.

## ⚙️ Installation

1.  **Téléchargez les fichiers** du bot (ou clonez le dépôt).

2.  **Installez les dépendances** nécessaires. Ouvrez un terminal ou une invite de commandes dans le dossier du bot et exécutez la commande suivante :
    ```bash
    pip install -r requirements.txt
    ```

## 🛠️ Configuration

La configuration se fait principalement dans 3 fichiers. Suivez attentivement ces étapes.

### 1. Fichier `.env` (à créer)

Ce fichier contiendra le token secret de votre bot.

1.  À la racine du projet (au même niveau que `main.py`), créez un fichier nommé `.env`.
2.  Ouvrez ce fichier et ajoutez la ligne suivante, en remplaçant `VOTRE_TOKEN_DE_BOT_ICI` par le vrai token de votre bot :

    ```
    token=VOTRE_TOKEN_DE_BOT_ICI
    ```

### 2. Fichier `PARAM.py`

Ce fichier contient tous les paramètres importants. Ouvrez `PARAM.py` et modifiez les valeurs suivantes :

```python
# Ligne 1
# Mettez votre propre ID d'utilisateur Discord ici. 
# Pour obtenir votre ID : activez le mode développeur, faites un clic droit sur votre profil et "Copier l'ID de l'utilisateur".
owners = [946098490654740580]

# Ligne 5
# L'ID du bot que vous voulez surveiller.
# Pour obtenir son ID : activez le mode développeur, faites un clic droit sur le profil du bot et "Copier l'ID de l'utilisateur".
BOT_ID = 1344712966351884431

# Ligne 6
# L'ID du salon dont le nom sera modifié (ex: 🟢・online / 🔴・offline).
# Pour obtenir son ID : activez le mode développeur, faites un clic droit sur le salon et "Copier l'ID du salon".
CHANNEL_ID = 1345710620200407123

# Ligne 7
# L'ID du message qui sera modifié dans le salon ci-dessus.
# Pour l'obtenir :
#   1. Envoyez un message temporaire (ex: "statut") dans le salon défini par CHANNEL_ID.
#   2. Faites un clic droit sur ce message et "Copier l'ID du message".
#   3. Collez l'ID ici.
MESSAGE_ID = 1346867347255721984

# Ligne 8
# L'ID du salon où les logs de changement de statut seront envoyés.
# Pour obtenir son ID : activez le mode développeur, faites un clic droit sur le salon et "Copier l'ID du salon".
LOGS_CHANNEL_ID = 1350443541867790406
```

### 3. Fichier `cog/statut.py` (Modification du Ping)

Lorsque le bot surveillé passe hors ligne, le Status Bot envoie une notification (un "ping") à un rôle. Vous devez configurer quel rôle sera notifié.

1.  Ouvrez le fichier `cog/statut.py`.
2.  Allez à la **ligne 130** (environ). Vous y trouverez :

    ```python
    # Ligne 130
    ping = await channel.send(content="<@&1350429004032770068>")
    ```

3.  Remplacez `1350429004032770068` par l'ID du rôle que vous souhaitez notifier.
    - **Pour obtenir l'ID d'un rôle** :
        1. Allez dans les `Paramètres du serveur` > `Rôles`.
        2. Faites un clic droit sur le rôle désiré et `Copier l'ID du rôle`.

## 🚀 Lancement du Bot

Une fois que tout est configuré :

1.  **Invitez votre Status Bot** sur votre serveur. Assurez-vous qu'il a les permissions de :
    - Voir les salons
    - Envoyer des messages
    - Gérer les messages (pour éditer le message de statut)
    - Gérer le salon (pour changer son nom)
2.  **Invitez le bot à surveiller** sur le même serveur. Le Status Bot ne peut pas voir son statut s'ils ne sont pas sur un serveur commun.
3.  Ouvrez un terminal dans le dossier du bot et lancez-le avec la commande :
    ```bash
    python main.py
    ```

Le bot devrait se connecter et commencer à surveiller votre bot cible !

## 🤖 Commandes

- `s%start [secondes]` : (Propriétaires seulement) Change la vitesse de rotation du statut du bot.
- `s%s <on|off>` : (Propriétaires seulement) Force manuellement le statut affiché à "en ligne" (`on`) ou "hors ligne" (`off`).
- `/ping-infos` : Affiche des informations techniques et des statistiques sur le Status Bot.