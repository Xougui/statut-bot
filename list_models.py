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

with open("models.txt", "w", encoding="utf-8") as f:
    for m in client.models.list():
        f.write(
            f"{m.name.replace('models/', '')}   |   {getattr(m, 'display_name', '')}\n"
        )
