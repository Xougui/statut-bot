import os
import sys

from dotenv import (
    load_dotenv,
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

models.sort(key=lambda m: getattr(m, "display_name", "") or "N/A")


max_len = max((len(m.name.replace("models/", "")) for m in models), default=20) + 4

with open("models.txt", "w", encoding="utf-8") as f:
    header = f"{'ID du Modèle':<{max_len}}| {"Nom d'affichage"}"
    f.write(header + "\n")
    f.write("-" * (len(header) + 15) + "\n")

    for m in models:
        name = m.name.replace("models/", "")
        display_name = getattr(m, "display_name", "") or "N/A"
        f.write(f"{name:<{max_len}}| {display_name}\n")

print(f"Terminé ! {len(models)} modèles ont été listés dans 'models.txt'.")
