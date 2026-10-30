"""Détection des prises : cache, Roboflow puis modèle local, limites."""
import json

import pytest

from src import constants as C
from tests.helpers import post_json

HOLDS = [{"x": 0.1, "y": 0.2, "w": 0.05, "h": 0.05}]


@pytest.fixture
def detecteurs(monkeypatch):
    calls = {"rf": 0, "local": 0}

    def rf(path):
        calls["rf"] += 1
        return HOLDS

    def local(path):
        calls["local"] += 1
        return HOLDS
    monkeypatch.setattr("src.routes.detection.detect_with_roboflow", rf)
    monkeypatch.setattr("src.routes.detection.detect_with_local_model", local)
    return calls


def detect(client, wall, force=False):
    return post_json(client, f"/api/wall/{wall}/detect_holds" + ("?force=1" if force else ""))


def test_roboflow_en_priorite_et_mise_en_cache(bob, decor, detecteurs, dbq):
    j = detect(bob, decor["wall"]).get_json()
    assert j["source"] == "roboflow" and j["holds"] == HOLDS and "cached" not in j
    assert json.loads(dbq("SELECT detected_holds FROM wall")[0][0]) == HOLDS and dbq("SELECT detected_source FROM wall")[0][0] == "roboflow"
    j = detect(bob, decor["wall"]).get_json()
    assert j["cached"] is True and detecteurs == {"rf": 1, "local": 0}


def test_force_relance_une_analyse(bob, decor, detecteurs):
    detect(bob, decor["wall"]); detect(bob, decor["wall"], force=True)
    assert detecteurs["rf"] == 2


def test_repli_sur_le_modele_local(bob, decor, monkeypatch, detecteurs, dbq):
    def boom(path):
        raise RuntimeError("crédits épuisés")
    monkeypatch.setattr("src.routes.detection.detect_with_roboflow", boom)
    j = detect(bob, decor["wall"]).get_json()
    assert j["source"] == "local" and dbq("SELECT detected_source FROM wall")[0][0] == "local"


def test_double_echec_n_est_pas_mis_en_cache(bob, decor, monkeypatch, dbq):
    def boom(path):
        raise RuntimeError("secret technique")
    monkeypatch.setattr("src.routes.detection.detect_with_roboflow", boom)
    monkeypatch.setattr("src.routes.detection.detect_with_local_model", boom)
    r = detect(bob, decor["wall"])
    assert r.status_code == 500 and r.get_json() == {"error": "detection_unavailable"}      # aucun détail technique côté client
    assert dbq("SELECT detected_holds FROM wall")[0][0] is None


def test_resultat_vide_non_enregistre(bob, decor, monkeypatch, dbq):
    monkeypatch.setattr("src.routes.detection.detect_with_roboflow", lambda p: [])
    assert detect(bob, decor["wall"]).get_json()["holds"] == []
    assert dbq("SELECT detected_holds FROM wall")[0][0] is None


def test_cache_corrompu_ignore(bob, decor, detecteurs, dbq_write):
    dbq_write("UPDATE wall SET detected_holds = 'pas du json'")
    assert "cached" not in detect(bob, decor["wall"]).get_json()


def test_limite_par_compte(bob, decor, detecteurs):
    for _ in range(C.DETECT_USER_MAX if hasattr(C, "DETECT_USER_MAX") else 10):
        assert detect(bob, decor["wall"], force=True).status_code == 200
    r = detect(bob, decor["wall"], force=True)
    assert r.status_code == 429 and r.get_json() == {"error": "detection_limited"}


def test_limite_globale(bob, decor, detecteurs, monkeypatch):
    monkeypatch.setattr("src.routes.detection.DETECT_DAILY_LIMIT", 2)
    detect(bob, decor["wall"], force=True); detect(bob, decor["wall"], force=True)
    assert detect(bob, decor["wall"], force=True).status_code == 429


def test_le_cache_ne_consomme_pas_de_credit(bob, decor, detecteurs, monkeypatch):
    monkeypatch.setattr("src.routes.detection.DETECT_DAILY_LIMIT", 1)
    detect(bob, decor["wall"])
    for _ in range(5):
        assert detect(bob, decor["wall"]).status_code == 200


def test_photo_manquante(bob, decor, detecteurs, app):
    import os
    os.remove(os.path.join(app.config["UPLOAD_FOLDER"], decor["image"]))
    assert detect(bob, decor["wall"]).status_code == 404


def test_acces(anon, bob, decor, prive, detecteurs):
    assert anon.post(f"/api/wall/{decor['wall']}/detect_holds").status_code in (400, 401, 302)
    assert bob.post(f"/api/wall/{decor['wall']}/detect_holds").status_code == 400      # CSRF
    assert detect(bob, 99).status_code == 404
    assert detect(bob, prive["wall"]).status_code == 404
    assert detecteurs["rf"] == 0
