"""
Nomme (ou retire) un administrateur depuis la console, par son pseudo.

    python scripts/make_admin.py MonPseudo          # le rend administrateur
    python scripts/make_admin.py MonPseudo --remove # lui retire le rôle

Utile pour nommer le tout premier administrateur : ensuite, la page /admin du
site permet de nommer d'autres administrateurs sans passer par ici.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config

DATABASE = Config.DATABASE


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)
    role = "user" if "--remove" in sys.argv else "admin"
    conn = sqlite3.connect(DATABASE, timeout=10)
    row = conn.execute("SELECT id, name FROM user WHERE LOWER(name) = LOWER(?)", (args[0],)).fetchone()
    if not row:
        print(f"Aucun compte avec le pseudo « {args[0]} ».")
        sys.exit(1)
    conn.execute("UPDATE user SET role = ? WHERE id = ?", (role, row[0]))
    try:   # trace dans le journal d'administration (affiché sur la page /admin)
        conn.execute("INSERT INTO admin_log(admin_id, admin_name, action, target) VALUES(NULL, ?, ?, ?)",
                     ("(console du serveur)", "Droits administrateur accordés" if role == "admin" else "Droits administrateur retirés",
                      f"{row[1]} (#{row[0]})"))
    except sqlite3.OperationalError:
        pass  # base pas encore mise à jour : le journal n'existe pas
    conn.commit()
    conn.close()
    print(f"« {row[1]} » a maintenant le rôle : {role}.")


if __name__ == "__main__":
    main()
