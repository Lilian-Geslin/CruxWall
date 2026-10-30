"""Fixtures communes : application sur base temporaire, clients connectés, accès direct à la base."""
import os
import tempfile

# Les tests ne touchent jamais à la vraie base ni aux vraies photos : tout est redirigé vers un dossier temporaire
# AVANT l'import de l'application (le mode « development » désactive le HTTPS forcé et le cookie « secure »).
os.environ["FLASK_SECRET_KEY"] = "cle-de-test-" + "x" * 30
os.environ["CRUXWALL_ENV"] = "development"
os.environ["AUTO_MAINTENANCE"] = "0"
os.environ["LEGAL_PUBLISHER_NAME"] = "Jean Test"
os.environ["LEGAL_CONTACT_EMAIL"] = "contact@exemple.fr"
os.environ.pop("TRUST_PROXY", None)
os.environ["CRUXWALL_DATABASE"] = os.path.join(tempfile.mkdtemp(prefix="cruxwall-tests-"), "jamais-utilisee.db")

import pytest

from src import create_app
from src.db import connect
from src.schema import init_db
from tests.helpers import PASSWORD, insert_user, register


@pytest.fixture(autouse=True)
def fast_settings(monkeypatch):
    """Réglages pensés pour les tests : hachage de mot de passe très léger, formulaire d'inscription sans délai minimal."""
    from werkzeug.security import generate_password_hash as real
    fast = lambda password, *a, **k: real(password, method="pbkdf2:sha256:1")
    monkeypatch.setattr("src.routes.auth.generate_password_hash", fast)
    monkeypatch.setattr("tests.helpers.generate_password_hash", fast)
    monkeypatch.setattr("src.services.antibot.REGISTER_MIN_SECONDS", 0)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def app(db_path, tmp_path):
    """Application neuve (base, photos et sauvegardes dans un dossier temporaire)."""
    return create_app({
        "DATABASE": db_path, "UPLOAD_FOLDER": str(tmp_path / "uploads"), "BACKUP_DIR": str(tmp_path / "backups"),
        "LEGACY_UPLOAD_FOLDER": str(tmp_path / "legacy"), "TESTING": True,
    })


@pytest.fixture
def conn(db_path):
    """Connexion directe à une base neuve (schéma créé) pour tester les services sans HTTP."""
    init_db(db_path)
    connection = connect(db_path)
    yield connection
    connection.close()


@pytest.fixture
def uid(conn):
    """Premier utilisateur (service)."""
    return insert_user(conn, "Lilian", "lilian@example.fr")


@pytest.fixture
def uid2(conn):
    """Second utilisateur (service), pour vérifier l'isolation des données."""
    return insert_user(conn, "Autre", "autre@example.fr")


@pytest.fixture
def anon(app):
    """Client HTTP non connecté."""
    return app.test_client()


@pytest.fixture
def alice(app):
    """Client HTTP connecté en tant qu'Alice (compte créé par /register)."""
    return register(app, "Alice", "alice@example.fr")[0]


@pytest.fixture
def bob(app, alice):
    """Second client HTTP, connecté avec un autre compte (même application, même base)."""
    return register(app, "Bob", "bob@example.fr")[0]


@pytest.fixture
def admin(app, dbq_write):
    """Client HTTP d'un administrateur."""
    client = register(app, "Admin", "admin@example.fr")[0]
    dbq_write("UPDATE user SET role = 'admin' WHERE name = 'Admin'")
    return client


@pytest.fixture
def dbq(db_path):
    """Lecture directe de la base pendant un test HTTP : dbq('SELECT ...', params) -> liste de lignes."""
    def query(sql, *params):
        c = connect(db_path)
        try:
            return c.execute(sql, params).fetchall()
        finally:
            c.close()
    return query


@pytest.fixture
def dbq_write(db_path):
    """Écriture directe dans la base pendant un test HTTP : dbq_write('UPDATE ...', params)."""
    def write(sql, *params):
        c = connect(db_path)
        try:
            c.execute(sql, params)
            c.commit()
        finally:
            c.close()
    return write
