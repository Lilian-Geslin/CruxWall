"""Service de détection : Roboflow (réseau simulé), modèle local (simulé), enregistrement du résultat. Aucun appel réseau réel."""
import io
import json
import urllib.error

import pytest

from src.services import detection


class Reponse:
    def __init__(self, data):
        self.data = json.dumps(data).encode()

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def photo(tmp_path):
    p = tmp_path / "m.jpg"
    p.write_bytes(b"jpeg")
    return str(p)


class TestRoboflow:
    def test_cle_absente(self, photo, monkeypatch):
        monkeypatch.delenv("ROBOFLOW_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="ROBOFLOW_API_KEY"):
            detection.detect_with_roboflow(photo)

    def test_conversion_en_proportions(self, photo, monkeypatch):
        monkeypatch.setenv("ROBOFLOW_API_KEY", "k")
        vu = {}

        def fake(req, timeout):
            vu["url"], vu["timeout"], vu["method"] = req.full_url, timeout, req.get_method()
            return Reponse({"image": {"width": 200, "height": 100},
                            "predictions": [{"x": 100, "y": 50, "width": 20, "height": 10}]})
        monkeypatch.setattr(detection.urllib.request, "urlopen", fake)
        assert detection.detect_with_roboflow(photo) == [{"x": 0.5, "y": 0.5, "w": 0.1, "h": 0.1}]
        assert vu["url"].startswith("https://detect.roboflow.com/") and "api_key=k" in vu["url"] and vu["timeout"] == 20 and vu["method"] == "POST"

    def test_aucune_prise(self, photo, monkeypatch):
        monkeypatch.setenv("ROBOFLOW_API_KEY", "k")
        monkeypatch.setattr(detection.urllib.request, "urlopen", lambda r, timeout: Reponse({"image": {"width": 10, "height": 10}, "predictions": []}))
        assert detection.detect_with_roboflow(photo) == []

    def test_dimensions_manquantes(self, photo, monkeypatch):
        monkeypatch.setenv("ROBOFLOW_API_KEY", "k")
        monkeypatch.setattr(detection.urllib.request, "urlopen", lambda r, timeout: Reponse({"predictions": []}))
        with pytest.raises(RuntimeError, match="dimensions"):
            detection.detect_with_roboflow(photo)

    def test_erreur_http_avec_message(self, photo, monkeypatch):
        monkeypatch.setenv("ROBOFLOW_API_KEY", "k")

        def fake(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 402, "x", {}, io.BytesIO(json.dumps({"message": "crédits épuisés"}).encode()))
        monkeypatch.setattr(detection.urllib.request, "urlopen", fake)
        with pytest.raises(RuntimeError, match="402.*crédits épuisés"):
            detection.detect_with_roboflow(photo)

    def test_erreur_http_sans_json(self, photo, monkeypatch):
        monkeypatch.setenv("ROBOFLOW_API_KEY", "k")

        def fake(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 500, "oups", {}, io.BytesIO(b"<html>"))
        monkeypatch.setattr(detection.urllib.request, "urlopen", fake)
        with pytest.raises(RuntimeError, match="500"):
            detection.detect_with_roboflow(photo)

    def test_pas_de_connexion(self, photo, monkeypatch):
        monkeypatch.setenv("ROBOFLOW_API_KEY", "k")

        def fake(req, timeout):
            raise urllib.error.URLError("hors ligne")
        monkeypatch.setattr(detection.urllib.request, "urlopen", fake)
        with pytest.raises(RuntimeError, match="pas de connexion"):
            detection.detect_with_roboflow(photo)


class Boite:
    def __init__(self, x1, y1, x2, y2):
        self.xyxy = [type("T", (), {"tolist": lambda s: [x1, y1, x2, y2]})()]


class TestModeleLocal:
    def test_modele_absent(self, photo, monkeypatch):
        monkeypatch.setattr(detection, "get_yolo_model", lambda: None)
        with pytest.raises(RuntimeError, match="best.pt introuvable"):
            detection.detect_with_local_model(photo)

    def test_paquet_absent(self, photo, monkeypatch):
        def boom():
            raise ImportError
        monkeypatch.setattr(detection, "get_yolo_model", boom)
        with pytest.raises(RuntimeError, match="ultralytics"):
            detection.detect_with_local_model(photo)

    def test_conversion(self, photo, monkeypatch):
        class Modele:
            def predict(self, path, conf, verbose):
                assert conf == 0.25
                return [type("R", (), {"orig_shape": (100, 200), "boxes": [Boite(80, 40, 120, 60)]})()]
        monkeypatch.setattr(detection, "get_yolo_model", lambda: Modele())
        assert detection.detect_with_local_model(photo) == [{"x": 0.5, "y": 0.5, "w": 0.2, "h": 0.2}]

    def test_get_yolo_model_sans_fichier(self, monkeypatch, tmp_path):
        monkeypatch.setattr(detection, "_yolo_model", None)
        monkeypatch.setattr(detection, "MODEL_PATH", str(tmp_path / "absent.pt"))
        assert detection.get_yolo_model() is None


def test_enregistrement(app, conn, add_wall):
    wid = add_wall()
    # save_detection ouvre la base de l'application : on la pointe vers celle de la fixture
    app.config["DATABASE"] = conn.execute("PRAGMA database_list").fetchone()[2]
    with app.app_context():
        detection.save_detection(wid, [{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}], "local")
    row = conn.execute("SELECT detected_holds, detected_source, detected_at FROM wall").fetchone()
    assert json.loads(row[0]) == [{"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}] and row[1] == "local" and row[2]


def test_limites_par_defaut():
    assert (detection.DETECT_USER_MAX, detection.DETECT_USER_WINDOW) == (10, 3600) and detection.DETECT_DAILY_LIMIT >= 1
