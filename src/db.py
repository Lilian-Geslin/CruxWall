"""Accès à la base SQLite.

`get_db()` ouvre une NOUVELLE connexion à chaque appel ; l'appelant la referme (`conn.close()`) quand il a fini.
Le COMMIT n'est pas automatique : chaque route qui écrit doit appeler `conn.commit()`.
"""
import sqlite3

from flask import current_app


def connect(path):
    """Ouvre une connexion SQLite dont les lignes s'utilisent comme des dictionnaires."""
    # timeout : si une autre requête est en train d'écrire, on attend (jusqu'à 10 s) au lieu d'échouer
    # tout de suite avec « database is locked ».
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    # SQLite ignore les clés étrangères par défaut : on les active pour qu'une ligne ne puisse jamais
    # pointer vers un mur/bloc/utilisateur inexistant.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db():
    """Nouvelle connexion à la base de l'application courante (à fermer par l'appelant)."""
    return connect(current_app.config["DATABASE"])
