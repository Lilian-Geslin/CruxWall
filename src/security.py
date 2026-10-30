"""Sécurité des requêtes : jeton CSRF, redirection HTTPS, relecture du compte, en-têtes HTTP (CSP, HSTS…), journaux.

`init_app` branche ces contrôles sur l'application (avant et après chaque requête)."""

import logging
import re
import secrets

from flask import g
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import request
from flask import session

from .config import FORCE_HTTPS, IS_DEV
from .db import get_db


def get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token

def _csrf_ok():
    expected = session.get("csrf_token", "")
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
    if not expected or not sent:
        return False
    return secrets.compare_digest(sent.encode("utf-8"), expected.encode("utf-8"))

def security_checks():
    # Jeton à usage unique, propre à cette requête, qui autorise nos scripts
    # en ligne (voir la politique CSP dans add_security_headers)
    g.csp_nonce = secrets.token_urlsafe(16)

    # Redirection vers HTTPS (derrière l'hébergeur, qui indique le protocole d'origine
    # dans X-Forwarded-Proto). On ne redirige que si l'en-tête dit explicitement
    # « http » : s'il est absent, rien ne se passe (pas de risque de boucle).
    if (FORCE_HTTPS and request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip().lower() == "http"):
        return redirect("https://" + request.host + request.full_path.rstrip("?"), code=301)

    if request.endpoint in (None, "static"):
        return None

    # 1) Toute requête qui modifie quelque chose doit porter le jeton CSRF
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not _csrf_ok():
        if request.path.startswith("/api/"):
            return jsonify({"error": "Session expirée : rechargez la page puis réessayez."}), 400
        return render_template("pages/error.html", title="Session expirée",
            message="Votre session a expiré ou la requête est invalide. Rechargez la page puis réessayez."
        ), 400

    # 2) Le compte et son rôle sont relus en base à chaque requête : un compte
    #    supprimé est déconnecté, un changement de rôle (ex. retrait des
    #    droits admin) s'applique tout de suite, sans attendre une reconnexion.
    if "user_id" in session:
        conn = get_db()
        row = conn.execute("SELECT name, role, session_version FROM user WHERE id = ?", (session["user_id"],)).fetchone()
        conn.close()
        if not row:
            session.clear()
        elif "sv" in session and session["sv"] != (row["session_version"] or 0):
            session.clear()  # le mot de passe a changé depuis l'ouverture de cette session
        else:
            if "sv" not in session:
                session["sv"] = row["session_version"] or 0  # anciennes sessions, d'avant cette version
            if session.get("user_name") != row["name"]:
                session["user_name"] = row["name"]
            if session.get("user_role") != row["role"]:
                session["user_role"] = row["role"]
    return None

def add_security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("X-Frame-Options", "DENY")  # interdit d'afficher le site dans une iframe
    resp.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), payment=()")
    if not IS_DEV:
        # Le navigateur n'ouvrira plus le site qu'en HTTPS (180 jours)
        resp.headers.setdefault("Strict-Transport-Security", "max-age=15552000")
    nonce = g.get("csp_nonce")
    if nonce and resp.mimetype == "text/html":
        # Content-Security-Policy : liste blanche de ce que la page a le droit de
        # charger/exécuter. Même si une faille laissait passer du HTML piégé, le
        # navigateur refuserait d'exécuter un script qui n'est pas le nôtre.
        resp.headers["Content-Security-Policy"] = "; ".join([
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}'",
            "style-src 'self' 'unsafe-inline'",
            "font-src 'self'",
            "img-src 'self' data: blob:",
            "connect-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ])
    return resp

class RedactSecretsFilter(logging.Filter):
    """Masque clés d'API, jetons et mots de passe qui apparaîtraient dans un message de journal."""
    _pattern = re.compile(r"((?:api_key|apikey|token|secret|password)=)[^&\s\"']+", re.I)

    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = self._pattern.sub(r"\1***", msg)
        if redacted != msg:
            record.msg, record.args = redacted, ()
        return True


def init_app(app):
    """Branche les fonctions ci-dessus sur l'application (appelé par create_app)."""
    app.before_request(security_checks)
    app.after_request(add_security_headers)
    # Les clés d'API, jetons et mots de passe n'apparaissent jamais dans les journaux
    for handler in list(app.logger.handlers) + list(logging.getLogger().handlers):
        handler.addFilter(RedactSecretsFilter())
