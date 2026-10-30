"""Détection automatique des prises : Roboflow en priorité, modèle local YOLOv8 (best.pt) en secours."""

import base64
import json
import os
import urllib.request, urllib.error

from ..config import BASE_DIR
from ..db import get_db


ROBOFLOW_PROJECT = os.environ.get("ROBOFLOW_PROJECT", "my-first-project-zrber")

ROBOFLOW_VERSION = os.environ.get("ROBOFLOW_VERSION", "2")

MODEL_PATH = os.path.join(BASE_DIR, "best.pt")

_yolo_model = None  # chargé une seule fois, au premier appel

def get_yolo_model():
    global _yolo_model
    if _yolo_model is None:
        if not os.path.exists(MODEL_PATH):
            return None
        from ultralytics import YOLO
        _yolo_model = YOLO(MODEL_PATH)
    return _yolo_model

def detect_with_roboflow(img_path):
    """Tente la détection via l'API Roboflow hébergée. Lève une exception si ça échoue."""
    api_key = os.environ.get("ROBOFLOW_API_KEY", "")
    if not api_key:
        raise RuntimeError("clé ROBOFLOW_API_KEY non configurée")

    with open(img_path, "rb") as f:
        b64 = base64.b64encode(f.read())

    url = (
        f"https://detect.roboflow.com/{ROBOFLOW_PROJECT}/{ROBOFLOW_VERSION}"
        f"?api_key={api_key}&confidence=40&overlap=30"
    )
    req = urllib.request.Request(
        url, data=b64,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
            detail = body.get("message") or body.get("error") or str(e)
        except Exception:
            detail = str(e)
        raise RuntimeError(f"erreur {e.code} — {detail}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"pas de connexion internet ({e.reason})")

    predictions = result.get("predictions", [])
    img_w = result.get("image", {}).get("width")
    img_h = result.get("image", {}).get("height")
    if not img_w or not img_h:
        raise RuntimeError("réponse Roboflow invalide (dimensions manquantes)")

    return [
        {"x": p["x"] / img_w, "y": p["y"] / img_h,
         "w": p["width"] / img_w, "h": p["height"] / img_h}
        for p in predictions
    ]

def detect_with_local_model(img_path):
    """Détection avec votre modèle local YOLOv8 (best.pt) : gratuit, illimité, hors-ligne."""
    try:
        model = get_yolo_model()
    except ImportError:
        raise RuntimeError("le paquet 'ultralytics' n'est pas installé (pip install ultralytics)")
    if model is None:
        raise RuntimeError(f"best.pt introuvable (attendu ici : {MODEL_PATH})")

    results = model.predict(img_path, conf=0.25, verbose=False)
    r = results[0]
    img_h, img_w = r.orig_shape
    holds = []
    for box in r.boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        holds.append({
            "x": ((x1 + x2) / 2) / img_w, "y": ((y1 + y2) / 2) / img_h,
            "w": (x2 - x1) / img_w, "h": (y2 - y1) / img_h,
        })
    return holds

DETECT_USER_MAX, DETECT_USER_WINDOW = 10, 3600   # 10 analyses par heure et par compte

try:
    DETECT_DAILY_LIMIT = int(os.environ.get("DETECT_DAILY_LIMIT", "100"))  # analyses par 24 h, tout le site
except ValueError:
    DETECT_DAILY_LIMIT = 100

def save_detection(wall_id, holds, source):
    conn = get_db()
    conn.execute(
        "UPDATE wall SET detected_holds = ?, detected_source = ?, detected_at = CURRENT_TIMESTAMP WHERE id = ?",
        (json.dumps(holds), source, wall_id)
    )
    conn.commit()
    conn.close()
