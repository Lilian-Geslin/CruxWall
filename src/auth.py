"""Authentification : session, décorateurs login_required et admin_required.

Le compte connecté est mémorisé dans la session Flask (cookie signé) ; la connexion / inscription
elles-mêmes sont dans routes/auth.py."""

from urllib.parse import quote

from flask import abort
from flask import redirect
from flask import request
from flask import session
from werkzeug.security import generate_password_hash


# Hash factice : on calcule toujours un hash au login, même quand l'email
# n'existe pas, pour que le temps de réponse ne révèle pas si le compte existe.
DUMMY_PASSWORD_HASH = generate_password_hash("mot-de-passe-factice-cruxwall")

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(f"/login?redirect={quote(request.path)}")
        return f(*args, **kwargs)
    return decorated

def start_session(user_id, name, role, sv=0):
    """
    Ouvre une session propre. On vide d'abord l'ancienne : un identifiant de
    session posé avant la connexion ne doit jamais servir après (fixation de session).
    """
    session.clear()
    session.permanent = True
    session["user_id"] = user_id
    session["user_name"] = name
    session["user_role"] = role
    session["sv"] = sv  # version de session : change quand le mot de passe change (déconnecte les autres appareils)

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(f"/login?redirect={quote(request.path)}")
        if session.get("user_role") != "admin":
            abort(403)
        return f(*args, **kwargs)
    return decorated
