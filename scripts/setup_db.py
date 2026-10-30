"""Crée ou met à jour la base de données (sans rien effacer).

    python scripts/setup_db.py            # crée les tables / colonnes manquantes
    python scripts/setup_db.py --reset    # DANGEREUX : efface TOUTE la base (PC de test uniquement)

L'application fait déjà la même mise à jour à chaque démarrage : ce script sert surtout à préparer une base neuve
ou à vérifier une migration. Ne jamais lancer --reset sur le serveur en ligne.
"""
import os
import sys

# Les scripts vivent dans scripts/ : on ajoute la racine du projet pour pouvoir importer `src`.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from src.config import Config
from src.schema import init_db

if __name__ == "__main__":
    if "--reset" in sys.argv:
        # DANGEREUX : efface toutes les données (comptes, murs, blocs...). Réservé au PC de test.
        if input("Cela EFFACE toute la base. Tape OUI pour confirmer : ").strip() == "OUI":
            if os.path.exists(Config.DATABASE):
                os.remove(Config.DATABASE)
                print("Ancienne base supprimée.")
        else:
            print("Annulé, rien n'a été effacé.")
            sys.exit(0)
    init_db(Config.DATABASE)
    print("Base prête.")
