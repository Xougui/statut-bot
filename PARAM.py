# --- PROPRIÉTAIRES DU BOT ---
# Mettez ici les IDs des utilisateurs qui auront les permissions de propriétaire sur le bot.
owners = [946098490654740580, 1178647820052467823]

# --- COULEUR DES EMBEDS ---
# Couleur par défaut pour les messages intégrés (embeds). Utilisez un format hexadécimal.
couleur = 0x42694B

# --- ID DU BOT À SURVEILLER ---
# L'ID de l'utilisateur du bot dont vous voulez suivre le statut.
BOT_ID = 1335228717403996160

# --- IDs DES CANAUX ET MESSAGES ---
# L'ID du salon textuel dont le nom sera modifié (ex: 🟢・online) et envoyé l'embed d'informations.
CHANNEL_ID = 1345710620200407123
# L'ID du salon où les logs (changements de statut) seront envoyés (sans mention).
LOGS_CHANNEL_ID = 1350443541867790406
# L'ID du rôle à mentionner dans les messages de statut envoyés dans CHANNEL_ID.
ROLE_ID = 1350429004032770068

# --- IDs DES CANAUX DE MISE À JOUR ---
UPDATE_CHANNEL_ID_FR = 1345064533173080166  # Salon français
UPDATE_CHANNEL_ID_EN = 1421773639761526824  # Salon anglais
UPDATE_CHANNEL_ID_TEST = 1350138595515568169  # Salon de test
UPDATE_ROLE_ID = 1350428823052746752  # Rôle à mentionner pour les mises à jour

# --- MODÈLE GEMINI ---
# Nom du modèle Gemini à utiliser pour la correction et la traduction.
GEMINI_MODEL = "gemini-2.5-flash"

# pipreqs . --force --encoding=utf8 --ignore .venv
# pip list --outdated | Select-String -Pattern '^\S+' | ForEach-Object { pip install --upgrade $_.Matches.Value }
# pip-review --auto

# ruff check . --fix
# ruff check . --fix --unsafe-fixes
# ruff format .

# --------------------------------------------------
# EMOJIS DISCORD
checkmark = "<:checkmark:1400837715066359981>"
crossmarck = "<:crossmark_color:1401216750191902910>"
online = "<:up:1400895319473913976>"
offline = "<:down:1400895329129205910>"
in_progress = "<:in_progress_color:1401216726330249358>"
maintenance = "<:maintenance:1400895308346429490>"
annonce = "<:annonce:1400906704643817584>"
test = "<:test:1400884178748178523>"

support_server = "https://discord.gg/RZHrtzwUC2"
