"""Connexion, inscription et déconnexion."""

from flask import Blueprint
from flask import redirect
from flask import render_template
from flask import request
from flask import session
from werkzeug.security import check_password_hash
from werkzeug.security import generate_password_hash

from ..auth import DUMMY_PASSWORD_HASH, start_session
from ..constants import EMAIL_RE, LOGIN_EMAIL_MAX, LOGIN_IP_MAX, LOGIN_PAIR_MAX, LOGIN_WINDOW, PASSWORD_MAX, PASSWORD_MIN, PSEUDO_RE, REGISTER_IP_MAX, REGISTER_WINDOW, TOO_MANY_MSG
from ..db import get_db
from ..services.antibot import form_token_ok
from ..services.ratelimit import client_ip, rl_count, rl_hit, rl_reset
from ..services.validation import normalize_email, safe_next_url


bp = Blueprint("auth", __name__)

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        session["redirect_after_login"] = safe_next_url(request.args.get("redirect"))
    error = None
    if request.method == "POST":
        email = normalize_email(request.form.get("email"))
        password = request.form.get("password", "")
        ip = client_ip()
        bucket_pair = f"login:pair:{email[:254]}|{ip}"
        bucket_email = f"login:email:{email[:254]}"
        bucket_ip = f"login:ip:{ip}"

        conn = get_db()
        if (rl_count(conn, bucket_pair, LOGIN_WINDOW) >= LOGIN_PAIR_MAX
                or rl_count(conn, bucket_ip, LOGIN_WINDOW) >= LOGIN_IP_MAX
                or rl_count(conn, bucket_email, LOGIN_WINDOW) >= LOGIN_EMAIL_MAX):
            conn.close()
            return render_template("auth/login.html", error=TOO_MANY_MSG), 429

        user = conn.execute("SELECT * FROM user WHERE LOWER(email) = ?", (email,)).fetchone()
        # Toujours un calcul de hash (même sans compte) : pas de différence de durée
        valid_length = len(password) <= PASSWORD_MAX
        stored_hash = user["password"] if user else DUMMY_PASSWORD_HASH
        password_ok = valid_length and check_password_hash(stored_hash, password)

        if not user or not password_ok:
            rl_hit(conn, bucket_pair)
            rl_hit(conn, bucket_email)
            rl_hit(conn, bucket_ip)
            conn.commit()
            conn.close()
            # Même message dans tous les cas : on ne révèle pas si l'email existe
            error = "Email ou mot de passe incorrect."
        else:
            rl_reset(conn, bucket_pair)
            conn.commit()
            conn.close()
            next_url = safe_next_url(session.get("redirect_after_login"))
            start_session(user["id"], user["name"], user["role"], user["session_version"] or 0)
            return redirect(next_url)
    return render_template("auth/login.html", error=error)

@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        session["redirect_after_login"] = safe_next_url(request.args.get("redirect"))
    error = None
    name = email = ""
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        email = normalize_email(request.form.get("email"))
        password = request.form.get("password") or ""
        bucket_ip = f"register:ip:{client_ip()}"

        conn = get_db()
        if rl_count(conn, bucket_ip, REGISTER_WINDOW) >= REGISTER_IP_MAX:
            conn.close()
            return render_template("auth/register.html", error=TOO_MANY_MSG, form_name=name, form_email=email), 429
        if request.form.get("company_url") or not form_token_ok(request.form.get("form_ts", "")):
            # Champ piège rempli (robot), ou formulaire envoyé trop vite / trop vieux / falsifié
            error = "Le formulaire a expiré ou a été envoyé trop vite. Rechargez la page puis réessayez."
        elif not request.form.get("accept_terms"):
            error = "Vous devez accepter les conditions d'utilisation et la politique de confidentialité."
        elif not PSEUDO_RE.match(name):
            error = "Pseudo invalide : 3 à 30 caractères, uniquement lettres (sans accents), chiffres, tiret (-) et underscore (_)."
        elif len(email) > 254 or not EMAIL_RE.match(email):
            error = "Adresse email invalide."
        elif not (PASSWORD_MIN <= len(password) <= PASSWORD_MAX):
            error = f"Le mot de passe doit contenir entre {PASSWORD_MIN} et {PASSWORD_MAX} caractères."
        elif conn.execute("SELECT id FROM user WHERE LOWER(email) = ?", (email,)).fetchone():
            error = "Un compte existe deja avec cet email."
        elif conn.execute("SELECT id FROM user WHERE LOWER(name) = LOWER(?)", (name,)).fetchone():
            error = "Ce pseudo est déjà pris, choisissez-en un autre."
        else:
            hashed = generate_password_hash(password)
            cursor = conn.execute(
                "INSERT INTO user(name, email, password, terms_accepted_at) VALUES(?, ?, ?, CURRENT_TIMESTAMP)",
                (name, email, hashed)
            )
            rl_hit(conn, bucket_ip)
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            next_url = safe_next_url(session.get("redirect_after_login"))
            start_session(user_id, name, "user")
            return redirect(next_url)
        conn.close()
    return render_template("auth/register.html", error=error, form_name=name, form_email=email)

@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/")
