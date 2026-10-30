"""Outils partagés par les tests : comptes, salles, murs et blocs fabriqués par les vraies routes (ou directement en base)."""
import io
import re

from PIL import Image
from werkzeug.security import generate_password_hash

PASSWORD = "motdepasse1"

HOLDS = [{"x": 0.1, "y": 0.2, "type": "start"}, {"x": 0.5, "y": 0.5, "type": "mid"}, {"x": 0.6, "y": 0.1, "type": "top"}]


def png(width=200, height=100, fmt="PNG"):
    """Petite image en mémoire, prête à être envoyée comme photo de mur."""
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "gray").save(buf, fmt)
    buf.seek(0)
    return buf


def csrf(client, path="/"):
    """Jeton CSRF de la session de `client`, lu dans un formulaire (ou la balise meta) de la page `path`."""
    html = client.get(path).get_data(as_text=True)
    found = re.search(r'name="csrf_token" value="([^"]+)"', html) or re.search(r'name="csrf-token" content="([^"]+)"', html)
    return found.group(1)


def post(client, path, data=None, **kwargs):
    """POST de formulaire avec jeton CSRF ajouté automatiquement."""
    data = dict(data or {})
    data.setdefault("csrf_token", csrf(client))
    return client.post(path, data=data, **kwargs)


def post_json(client, path, payload=None, **kwargs):
    """POST JSON avec l'en-tête X-CSRF-Token."""
    return client.post(path, json=payload if payload is not None else {}, headers={"X-CSRF-Token": csrf(client)}, **kwargs)


def register(app, name, email, password=PASSWORD, terms=True, **extra):
    """Crée un compte par le formulaire d'inscription ; renvoie (client connecté, réponse)."""
    client = app.test_client()
    html = client.get("/register").get_data(as_text=True)
    data = {
        "csrf_token": re.search(r'name="csrf_token" value="([^"]+)"', html).group(1),
        "form_ts": re.search(r'name="form_ts" value="([^"]+)"', html).group(1),
        "name": name, "email": email, "password": password,
    }
    if terms:
        data["accept_terms"] = "1"
    data.update(extra)
    return client, client.post("/register", data=data)


def insert_user(conn, name="Lilian", email="lilian@example.fr", password=PASSWORD, role="user"):
    """Insère un compte directement en base (sans passer par HTTP) ; renvoie son identifiant."""
    cur = conn.execute("INSERT INTO user(name, email, password, role) VALUES(?,?,?,?)",
                       (name, email, generate_password_hash(password), role))
    conn.commit()
    return cur.lastrowid


def create_gym(client, name, private=False, location="Marseille"):
    data = {"name": name, "location": location}
    if private:
        data["is_private"] = "1"
    client.post("/gym/new", data={**data, "csrf_token": csrf(client, "/gyms")})


def create_wall(client, name, gym_id=None, private=False):
    data = {"name": name, "csrf_token": csrf(client, "/wall/new"), "image": (png(), "mur.png")}
    if gym_id:
        data["gym_id"] = str(gym_id)
    if private:
        data["is_private"] = "1"
    return client.post("/wall/new", data=data, content_type="multipart/form-data")


def block_payload(wall_id, name="Bloc A", **over):
    payload = {"wall_id": wall_id, "name": name, "grade": "6a", "color": "#3b82f6", "description": "", "holds": HOLDS}
    payload.update(over)
    return payload


def create_block(client, wall_id, name="Bloc A", **over):
    """Crée un bloc par l'API de l'éditeur ; renvoie la réponse (JSON : block_id)."""
    return post_json(client, "/api/block/save", block_payload(wall_id, name, **over))


def row(conn, sql, *params):
    return conn.execute(sql, params).fetchone()


def scalar(conn, sql, *params):
    return conn.execute(sql, params).fetchone()[0]
