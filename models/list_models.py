import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from google import genai

# Détermine le chemin absolu du dossier contenant ce script
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
api_key = os.getenv("GEMINI_API")
if not api_key:
    print(
        "Erreur : GEMINI_API introuvable. Vérifiez votre fichier .env.",
        file=sys.stderr,
    )
    sys.exit(1)

client = genai.Client(api_key=api_key)


def main() -> None:
    print("Récupération de la liste des modèles...")
    try:
        models = list(client.models.list())
    except Exception as e:
        print(f"Erreur lors de la connexion à l'API Gemini : {e}", file=sys.stderr)
        return

    def get_category(display_name: str) -> str:
        dn = display_name.lower()
        if dn.startswith("gemini 2.0"):
            return "gemini 2.0"
        if dn.startswith("gemini 2.5"):
            return "gemini 2.5"
        if dn.startswith("gemini 3"):
            return "gemini 3"
        if dn.startswith("gemini embedding"):
            return "gemini embedding"
        if "latest" in dn:
            return "gemini 9 latest"
        if dn.startswith("gemini"):
            return "gemini other"
        if dn.startswith("gemma"):
            return "gemma"
        if dn.startswith("imagen"):
            return "imagen"
        if dn.startswith("veo"):
            return "veo"
        if dn.startswith("nano banana"):
            return "nano banana"
        if "embedding" in dn:
            return "embedding"
        return "other"

    models.sort(
        key=lambda m: (
            get_category(getattr(m, "display_name", "") or "N/A") == "other",
            get_category(getattr(m, "display_name", "") or "N/A"),
            getattr(m, "display_name", "") or "N/A",
        )
    )

    output_file = BASE_DIR / "models.txt"

    # Préparation des données pour le tableau
    headers = [
        "ID du Modèle",
        "Nom d'affichage",
        "Input Token",
        "Output Token",
        "Description",
    ]
    data = []
    last_category = None

    for m in models:
        name = m.name.replace("models/", "")
        display_name = getattr(m, "display_name", "") or "N/A"

        current_category = get_category(display_name)
        if last_category is not None and current_category != last_category:
            data.append([])
        last_category = current_category

        input_limit = str(getattr(m, "input_token_limit", "N/A"))
        output_limit = str(getattr(m, "output_token_limit", "N/A"))

        desc = getattr(m, "description", "") or ""
        desc = desc.replace("\n", " ").strip()

        data.append([name, display_name, input_limit, output_limit, desc])

    # Calcul des largeurs de colonnes
    col_widths = [len(h) for h in headers]
    for row in data:
        if not row:
            continue
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    # Ajout d'un peu d'espace (padding)
    col_widths = [w + 6 for w in col_widths]

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            # Création de la ligne d'en-tête
            header_line = "".join(
                f"{h:<{w}}" for h, w in zip(headers, col_widths, strict=False)
            )
            f.write(header_line.rstrip() + "\n")

            # Ligne de séparation
            separator_line = "".join("-" * (w - 1) + " " for w in col_widths)
            f.write(separator_line.rstrip() + "\n")

            # Écriture des données
            for row in data:
                if not row:
                    f.write("\n")
                    continue
                line = "".join(
                    f"{cell:<{w}}" for cell, w in zip(row, col_widths, strict=False)
                )
                f.write(line.rstrip() + "\n")

        print(
            f"Terminé ! {len(models)} modèles ont été listés dans '{output_file.name}' avec plus de détails."
        )
    except OSError as e:
        print(f"Erreur lors de l'écriture du fichier : {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
