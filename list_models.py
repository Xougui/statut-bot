import os
import sys

from dotenv import (
    load_dotenv,  # Utilisé pour charger les variables d'environnement (le token) depuis un fichier .env
)
from google import genai

load_dotenv()
api_key = os.getenv("GEMINI_API")
if not api_key:
    print(
        "Error: GEMINI_API not found. Please set it as an environment variable.",
        file=sys.stderr,
    )
    sys.exit(1)

client = genai.Client(api_key=api_key)

print("Récupération de la liste des modèles...")
models = list(client.models.list())
# Tri des modèles par ordre alphabétique de leur nom d'affichage pour un rangement propre
models.sort(key=lambda m: getattr(m, "display_name", "") or "N/A")

# Calcul de la largeur maximale pour l'alignement (ID + marge)
max_len = max((len(m.name.replace("models/", "")) for m in models), default=20) + 4

with open("models.txt", "w", encoding="utf-8") as f:
    # Écriture de l'en-tête
    header = f"{'ID du Modèle':<{max_len}}| {"Nom d'affichage"}"
    f.write(header + "\n")
    f.write("-" * (len(header) + 15) + "\n")

    for m in models:
        name = m.name.replace("models/", "")
        display_name = getattr(m, "display_name", "") or "N/A"
        f.write(f"{name:<{max_len}}| {display_name}\n")

print(f"Terminé ! {len(models)} modèles ont été listés dans 'models.txt'.")
