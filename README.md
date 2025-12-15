# Status Bot - Surveillez vos Bots et Annoncez vos Mises à Jour

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![Discord.py](https://img.shields.io/badge/discord.py-2.0%2B-5865F2)
![Status](https://img.shields.io/badge/status-active-success)

Bienvenue sur le **Status Bot** ! Ce projet est conçu pour surveiller l'état de vos bots Discord et gérer vos annonces de mises à jour avec l'aide de l'intelligence artificielle.

## ✨ Fonctionnalités Principales

1.  **Surveillance Automatique** : Vérifie le statut d'un bot cible (En ligne, Hors ligne, Maintenance) toutes les 5 secondes.
2.  **Affichage Dynamique** :
    *   Met à jour automatiquement le nom d'un salon (ex: `🟢・online`).
    *   Gère un message (Embed) de statut qui se met à jour en temps réel.
    *   Recrée automatiquement le message de statut s'il est supprimé.
3.  **Gestion des Mises à Jour (IA)** : Rédigez vos patch notes en français, l'IA (Google Gemini) corrige le texte et le traduit automatiquement en anglais.
4.  **Système de Versionning** : Gestion automatisée des numéros de version et déploiement rapide.

---

## 📋 Prérequis (Ce qu'il vous faut avant de commencer)

Avant d'installer le bot, assurez-vous d'avoir les éléments suivants :

1.  **Python 3.9+** : Le logiciel qui permet de faire tourner le code.
    *   [Télécharger Python ici](https://www.python.org/downloads/) (Cochez bien la case **"Add Python to PATH"** lors de l'installation !).

2.  **Un Bot Discord** :
    *   Allez sur le [Portail des Développeurs Discord](https://discord.com/developers/applications).
    *   Créez une "New Application", puis allez dans l'onglet **Bot**.
    *   Cliquez sur **Reset Token** et copiez ce token (gardez-le secret !).
    *   ⚠️ **IMPORTANT** : Dans la section "Privileged Gateway Intents" (juste en dessous), activez **PRESENCE INTENT**, **SERVER MEMBERS INTENT** et **MESSAGE CONTENT INTENT**. Sans ça, le bot ne verra rien !

3.  **Une Clé API Google Gemini** (pour les annonces de mise à jour) :
    *   Allez sur [Google AI Studio](https://aistudio.google.com/app/apikey).
    *   Créez une clé API gratuite.

---

## 🛠️ Installation (Pas à pas)

### 1. Télécharger le projet
Si vous avez téléchargé le fichier `.zip`, extrayez-le dans un dossier de votre choix.
Si vous connaissez `git`, vous pouvez cloner le dépôt :
```bash
git clone https://github.com/Xougui/statut-bot.git
cd status-bot
```

### 2. Créer un "Environnement Virtuel" (Recommandé)
Cela permet d'isoler les fichiers du bot de votre ordinateur pour éviter les conflits.
Ouvrez votre terminal (Invite de commandes ou PowerShell sur Windows, Terminal sur Mac/Linux) dans le dossier du bot.

*   **Sur Windows :**
    ```bash
    python -m venv venv
    venv\Scripts\activate
    ```
    *(Vous verrez `(venv)` apparaître au début de la ligne, c'est bon signe !)*

*   **Sur Mac/Linux :**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

### 3. Installer les dépendances
Toujours dans le terminal (avec `(venv)` activé), tapez :
```bash
pip install -r requirements.txt
```
Cela va télécharger tout ce dont le bot a besoin (`discord.py`, `google-genai`, etc.).

---

## ⚙️ Configuration (Les fichiers à modifier)

Il y a deux fichiers à configurer pour que le bot fonctionne sur VOTRE serveur.

### 1. Le fichier `.env` (Vos mots de passe secrets)
Créez un nouveau fichier nommé `.env` (juste `.env`, sans rien avant) à la racine du dossier (à côté de `main.py`).
Ouvrez-le avec un éditeur de texte (Bloc-notes, VS Code...) et collez ceci en remplaçant par vos valeurs :

```env
token=VOTRE_TOKEN_DISCORD_ICI
GEMINI_API=VOTRE_CLE_GOOGLE_GEMINI_ICI
```
*   `token` : Le token de votre bot Discord (voir Prérequis).
*   `GEMINI_API` : La clé API de Google AI Studio.

### 2. Le fichier `PARAM.py` (Vos IDs Discord)
Ouvrez le fichier `PARAM.py`. Vous devez remplacer les chiffres par les IDs de votre serveur.
*Pour avoir les IDs : Sur Discord, allez dans Paramètres > Avancés > Activez le Mode Développeur. Ensuite, faites Clic Droit > Copier l'ID sur les salons/rôles/utilisateurs.*

Explications des variables dans `PARAM.py` :
*   `owners` : Votre ID utilisateur (pour avoir accès aux commandes admin).
*   `BOT_ID` : L'ID du bot que vous voulez surveiller.
*   `CHANNEL_ID` : L'ID du salon textuel qui changera de nom (ex: 🟢・online).
*   `LOGS_CHANNEL_ID` : L'ID d'un salon privé où le bot enverra l'historique des changements (Logs).
*   `ROLE_ID` : L'ID du rôle à mentionner ("ping") quand le bot surveillé tombe en panne.

> [!NOTE]
> Le bot créera automatiquement un fichier `data/statut.json` pour se souvenir de l'ID du message de statut. Si vous supprimez le message sur Discord, le bot en créera un nouveau automatiquement.*

---

## 🚀 Lancement du Bot

1.  Assurez-vous que votre terminal est ouvert dans le dossier du bot et que l'environnement virtuel est activé (`(venv)`).
2.  Lancez la commande :
    ```bash
    python main.py
    ```
3.  Si tout va bien, vous verrez un message indiquant que le bot est connecté ("Bot connecté en tant que ...").

---

## 🤖 Utilisation

### Surveillance Automatique
Le bot vérifie toutes les 5 secondes si le `BOT_ID` est en ligne.
*   S'il passe hors ligne, le bot modifie le nom du salon, l'embed du message, et ping le rôle configuré.
*   S'il revient en ligne, il remet tout au vert.

### Commandes (Slash Commands)
Tapez `/` dans Discord pour voir les commandes disponibles.

*   `/statut mode:<choix>` (Admin uniquement) :
    *   Permet de forcer le statut (utile pour tester).
    *   Modes : `Online`, `Offline`, `Maintenance`, `Automatique`.
    *   Vous pouvez ajouter une `raison` qui s'affichera sur le message de statut.

*   `/update` (Admin uniquement) :
    *   Permet de créer une annonce de mise à jour.
    *   Une fenêtre s'ouvre pour entrer les changements.
    *   L'IA va automatiquement corriger votre texte et le traduire en anglais !

*   `/ping-infos` :
    *   Affiche la latence du bot.
