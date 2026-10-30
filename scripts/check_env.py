"""
Vérifie le fichier .env du SERVEUR, sans jamais afficher de valeur secrète.

    python scripts/check_env.py

À lancer dans la console Bash de PythonAnywhere (dossier du projet, virtualenv actif).
Affiche OK / ATTENTION / ERREUR pour chaque réglage important et dit quoi faire.
"""
import os
import stat
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")

KNOWN = {
    "FLASK_SECRET_KEY", "CRUXWALL_ENV", "TRUST_PROXY", "FORCE_HTTPS", "AUTO_MAINTENANCE", "ROBOFLOW_API_KEY", "ROBOFLOW_PROJECT",
    "ROBOFLOW_VERSION", "MAX_UPLOADS_MB", "DETECT_DAILY_LIMIT", "BACKUP_DIR", "SQLITE_WAL", "CRUXWALL_DATABASE",
    "LEGAL_PUBLISHER_NAME", "LEGAL_PUBLISHER_ADDRESS", "LEGAL_CONTACT_EMAIL", "LEGAL_HOST",
}

results = []  # (niveau, message)


def add(level, message):
    results.append((level, message))


def main():
    if not os.path.exists(ENV_PATH):
        print(f"ERREUR : aucun fichier .env dans {BASE_DIR}")
        print("Il doit être dans le même dossier que run.py (voir README, section Configuration).")
        sys.exit(1)

    try:
        from dotenv import dotenv_values
    except ImportError:
        print("ERREUR : python-dotenv n'est pas installé (le virtualenv est-il activé ?).")
        sys.exit(1)
    values = dotenv_values(ENV_PATH)

    # --- syntaxe : lignes sans « = » ---
    with open(ENV_PATH, encoding="utf-8", errors="replace") as f:
        for number, line in enumerate(f, 1):
            text = line.strip()
            if text and not text.startswith("#") and "=" not in text:
                add("ATTENTION", f"ligne {number} : pas de « = » (ligne ignorée ; deux réglages collés sur une même ligne ?)")

    # --- clé secrète ---
    key = values.get("FLASK_SECRET_KEY") or ""
    if len(key) < 16:
        add("ERREUR", "FLASK_SECRET_KEY absente ou trop courte (l'appli refuse de démarrer sans elle).")
    elif len(key) < 32 or any(w in key.lower() for w in ("chaine_aleatoire", "changeme", "secret", "motdepasse", "password")):
        add("ATTENTION", f"FLASK_SECRET_KEY faible ({len(key)} caractères ou valeur d'exemple). Génère-en une : "
                         "python -c \"import secrets; print(secrets.token_urlsafe(48))\" puis remplace-la dans .env "
                         "(tout le monde sera déconnecté, c'est normal).")
    else:
        add("OK", f"FLASK_SECRET_KEY présente ({len(key)} caractères).")

    # --- mode production ---
    if (values.get("CRUXWALL_ENV") or "").strip().lower() == "development":
        add("ERREUR", "CRUXWALL_ENV=development : à SUPPRIMER sur le serveur (réservé à ton PC).")
    else:
        add("OK", "Mode production (CRUXWALL_ENV absent ou différent de « development »).")

    # --- proxy / HTTPS ---
    if values.get("TRUST_PROXY") == "1":
        add("OK", "TRUST_PROXY=1 (la vraie adresse IP des visiteurs est utilisée).")
    else:
        add("ERREUR", "TRUST_PROXY=1 manquant : toutes les limitations d'essais se feront sur l'IP de l'hébergeur. Ajoute la ligne.")
    if values.get("FORCE_HTTPS") == "0":
        add("ATTENTION", "FORCE_HTTPS=0 : la redirection automatique vers HTTPS est désactivée.")

    # --- pages légales ---
    for name in ("LEGAL_PUBLISHER_NAME", "LEGAL_CONTACT_EMAIL"):
        if (values.get(name) or "").strip():
            add("OK", f"{name} renseigné.")
        else:
            add("ATTENTION", f"{name} manquant ou vide : les pages légales affichent un rappel jaune.")

    # --- détection IA (information) ---
    add("OK" if values.get("ROBOFLOW_API_KEY") else "INFO",
        "ROBOFLOW_API_KEY présente." if values.get("ROBOFLOW_API_KEY") else
        "ROBOFLOW_API_KEY absente : la détection en ligne est désactivée (les prises se placent à la main).")

    # --- noms inconnus (fautes de frappe) ---
    for name in sorted(k for k in values if k not in KNOWN):
        add("ATTENTION", f"nom de réglage inconnu : « {name} » (faute de frappe ? il sera ignoré).")

    # --- droits du fichier ---
    mode = stat.S_IMODE(os.stat(ENV_PATH).st_mode)
    if mode & 0o077:
        add("ATTENTION", f"droits du fichier .env : {oct(mode)[2:]} (lisible par d'autres). Corrige avec : chmod 600 .env")
    else:
        add("OK", "Droits du fichier .env corrects (privé).")

    # --- .env suivi par Git ? ---
    try:
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", ".env"], cwd=BASE_DIR,
                                 capture_output=True, text=True).returncode == 0
        if tracked:
            add("ERREUR", ".env est suivi par Git (ses secrets sont dans le dépôt). Retire-le : git rm --cached .env, "
                          "puis change FLASK_SECRET_KEY et les clés qu'il contenait.")
        else:
            add("OK", ".env n'est pas suivi par Git.")
    except OSError:
        pass

    order = {"ERREUR": 0, "ATTENTION": 1, "INFO": 2, "OK": 3}
    for level, message in sorted(results, key=lambda r: order[r[0]]):
        print(f"[{level:9}] {message}")
    errors = sum(1 for level, _ in results if level == "ERREUR")
    warnings = sum(1 for level, _ in results if level == "ATTENTION")
    print(f"\n{errors} erreur(s), {warnings} attention(s).")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
