"""Pages d'erreur : HTML pour les pages, JSON pour /api/, aucun détail technique affiché."""
import sqlite3

import pytest
from flask import abort

from tests.helpers import csrf


@pytest.fixture
def piege(app):
    """Routes jetables qui déclenchent chaque type d'erreur."""
    for code in (400, 403, 404, 405, 429):
        app.add_url_rule(f"/test-{code}", f"t{code}", lambda c=code: abort(c))
        app.add_url_rule(f"/api/test-{code}", f"a{code}", lambda c=code: abort(c))

    def boom():
        raise RuntimeError("détail technique secret")

    def integrity():
        raise sqlite3.IntegrityError("UNIQUE constraint failed: user.email")
    app.add_url_rule("/test-500", "t500", boom)
    app.add_url_rule("/api/test-500", "a500", boom)
    app.add_url_rule("/test-409", "t409", integrity)
    app.add_url_rule("/api/test-409", "a409", integrity)
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.config["TESTING"] = False
    return app


@pytest.mark.parametrize("code,titre", [
    (400, "Requête invalide"), (403, "Accès refusé"), (404, "Page introuvable"), (405, "Action non autorisée"),
    (429, "Trop de demandes"), (500, "Erreur du serveur"), (409, "Conflit"),
])
def test_page_html(piege, anon, code, titre):
    r = anon.get(f"/test-{code}")
    assert r.status_code == code and titre in r.get_data(as_text=True) and "<html" in r.get_data(as_text=True)


@pytest.mark.parametrize("code", [400, 403, 404, 405, 429, 500, 409])
def test_json_pour_les_api(piege, anon, code):
    r = anon.get(f"/api/test-{code}")
    assert r.status_code == code and r.is_json and "error" in r.get_json()


def test_aucun_detail_technique(piege, anon):
    for path in ("/test-500", "/api/test-500", "/test-409", "/api/test-409"):
        body = anon.get(path).get_data(as_text=True)
        assert "secret" not in body and "UNIQUE" not in body and "Traceback" not in body


def test_404_reel(anon):
    r = anon.get("/cette-page-n-existe-pas")
    assert r.status_code == 404 and "Page introuvable" in r.get_data(as_text=True)


def test_405_reel(anon):
    assert anon.post("/gyms", data={}).status_code in (400, 405)


def test_fichier_trop_gros_api_json(alice, app):
    app.config["MAX_CONTENT_LENGTH"] = 100
    r = alice.post("/api/gym/quick_create", data={"name": "x" * 500, "csrf_token": "x"})
    assert r.status_code == 413 and r.get_json() == {"error": "Fichier trop volumineux."}


def test_page_d_erreur_garde_la_navigation(anon):
    page = anon.get("/introuvable").get_data(as_text=True)
    assert 'href="/"' in page
