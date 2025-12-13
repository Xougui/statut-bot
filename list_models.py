import os
import sys

from dotenv import (
    load_dotenv,  # Utilisé pour charger les variables d'environnement (le token) depuis un fichier .env
)
import google.generativeai as genai

load_dotenv()
api_key = os.getenv("GEMINI_API")
if not api_key:
    print(
        "Error: GEMINI_API not found. Please set it as an environment variable.",
        file=sys.stderr,
    )
    sys.exit(1)

genai.configure(api_key=api_key)

for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(m.name)
