"""
Vérifie si les bibliothèques utilisées par CruxWall ont des mises à jour ou des failles connues.

À lancer sur PythonAnywhere (console Bash, environnement virtuel activé) environ une fois par mois :

    python scripts/check_updates.py

1) Liste les paquets épinglés dans requirements-pythonanywhere.txt qui ont une version plus récente.
2) Si l'outil « pip-audit » est installé (pip install pip-audit), cherche les failles de sécurité connues.

Ce script N'INSTALLE ni ne MODIFIE rien : il informe seulement. Pour mettre à jour un paquet :
modifier la version dans requirements-pythonanywhere.txt ET requirements.txt, puis
    pip install -r requirements-pythonanywhere.txt
vérifier le site, et recharger l'application (onglet Web > Reload).
"""
import json
import os
import re
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REQ = os.path.join(BASE_DIR, "requirements-pythonanywhere.txt")


def pinned():
    out = {}
    try:
        with open(REQ, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([^\s#]+)", line)
                if m:
                    out[m.group(1).lower().replace("_", "-")] = m.group(2)
    except OSError:
        print(f"Fichier introuvable : {REQ}")
    return out


def major(version):
    try:
        return int(version.split(".")[0])
    except ValueError:
        return -1


def check_outdated(pins):
    print("=== 1) Versions plus récentes disponibles ===")
    try:
        res = subprocess.run([sys.executable, "-m", "pip", "list", "--outdated", "--format=json"],
                             capture_output=True, text=True, timeout=180)
        data = json.loads(res.stdout or "[]")
    except (subprocess.SubprocessError, ValueError, OSError) as e:
        print(f"Impossible d'interroger pip ({e}). Réseau indisponible ?")
        return
    if res.returncode != 0 and not data:
        print("pip n'a pas pu vérifier les versions (réseau indisponible ?).")
        return
    found = False
    for p in sorted(data, key=lambda x: x["name"].lower()):
        name = p["name"].lower().replace("_", "-")
        if name not in pins:
            continue
        found = True
        kind = "MAJEURE (à tester avec soin)" if major(p["latest_version"]) > major(p["version"]) else "mineure / correctif"
        print(f"  {p['name']:<16} installée {p['version']:<10} -> dernière {p['latest_version']:<10} [{kind}]")
    if not found:
        print("  Tout est à jour.")


def run_audit():
    print("\n=== 2) Failles de sécurité connues (pip-audit) ===")
    try:
        res = subprocess.run([sys.executable, "-m", "pip_audit", "-r", REQ], capture_output=True, text=True, timeout=300)
    except (subprocess.SubprocessError, OSError) as e:
        print(f"pip-audit n'a pas pu s'exécuter : {e}")
        return
    text = (res.stdout + res.stderr).strip()
    if "No module named pip_audit" in text:
        print("  pip-audit n'est pas installé. Pour l'installer : pip install pip-audit, puis relancer ce script.")
    elif res.returncode == 0:
        print("  Aucune faille connue dans les versions épinglées.")
    else:
        print(text)
        print("\n  -> Mettez à jour les paquets signalés (voir l'en-tête de ce fichier).")


if __name__ == "__main__":
    pins = pinned()
    print(f"{len(pins)} paquets épinglés dans {os.path.basename(REQ)}.\n")
    check_outdated(pins)
    run_audit()
