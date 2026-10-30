"""Limitation des tentatives (connexion, inscription, codes d'accès, quotas), stockée dans la table auth_attempt.

Stockée en base plutôt qu'en mémoire : PythonAnywhere lance plusieurs processus, une limite gardée en mémoire serait contournable."""

import os
import time

from flask import request
from flask import session

from ..constants import UNLOCK_IP_MAX, UNLOCK_IP_WINDOW, UNLOCK_USER_MAX, UNLOCK_USER_WINDOW


def client_ip():
    """
    Adresse IP du visiteur. Derrière le serveur de l'hébergeur, l'adresse vue
    par Flask est celle du serveur frontal : avec TRUST_PROXY=1 dans le .env,
    on lit celle qu'il transmet (X-Real-IP / X-Forwarded-For).
    """
    if os.environ.get("TRUST_PROXY") == "1":
        ip = request.headers.get("X-Real-IP", "").strip()
        if not ip:
            fwd = request.headers.get("X-Forwarded-For", "")
            ip = fwd.split(",")[-1].strip() if fwd else ""
        if ip:
            return ip[:64]
    return request.remote_addr or "inconnue"

def rl_count(conn, bucket, window_seconds):
    since = int(time.time()) - window_seconds
    return conn.execute(
        "SELECT COUNT(*) AS n FROM auth_attempt WHERE bucket = ? AND ts >= ?", (bucket, since)
    ).fetchone()["n"]

def rl_hit(conn, bucket):
    now = int(time.time())
    conn.execute("INSERT INTO auth_attempt(bucket, ts) VALUES(?, ?)", (bucket, now))
    conn.execute("DELETE FROM auth_attempt WHERE ts < ?", (now - 24 * 3600,))

def rl_reset(conn, bucket):
    conn.execute("DELETE FROM auth_attempt WHERE bucket = ?", (bucket,))

def unlock_rate_limited(conn):
    return (rl_count(conn, f"unlock:user:{session['user_id']}", UNLOCK_USER_WINDOW) >= UNLOCK_USER_MAX
            or rl_count(conn, f"unlock:ip:{client_ip()}", UNLOCK_IP_WINDOW) >= UNLOCK_IP_MAX)

def unlock_register_failure(conn):
    rl_hit(conn, f"unlock:user:{session['user_id']}")
    rl_hit(conn, f"unlock:ip:{client_ip()}")
