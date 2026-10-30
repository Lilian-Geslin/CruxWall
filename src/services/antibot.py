"""Anti-robots du formulaire d'inscription : jeton daté signé (un humain met plus de 2 s à remplir le formulaire)."""

from datetime import datetime
from datetime import timezone

from flask import current_app
from itsdangerous import URLSafeTimedSerializer

from ..constants import REGISTER_MAX_SECONDS, REGISTER_MIN_SECONDS




def _signer():
    """Signataire des jetons de formulaire (créé à la demande : la clé secrète appartient à l'application courante)."""
    return URLSafeTimedSerializer(current_app.secret_key, salt="cruxwall-register-form")

def make_form_token():
    return _signer().dumps("register")

def form_token_ok(token):
    try:
        value, issued_at = _signer().loads(token, max_age=REGISTER_MAX_SECONDS, return_timestamp=True)
    except Exception:
        return False
    if value != "register":
        return False
    return (datetime.now(timezone.utc) - issued_at).total_seconds() >= REGISTER_MIN_SECONDS
