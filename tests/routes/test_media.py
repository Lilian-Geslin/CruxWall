"""Service des photos /media/<fichier> : contrôle d'accès, 404 uniforme, en-têtes de cache."""
import os

from tests.helpers import create_wall


def test_photos_hors_du_dossier_static(anon, app, decor):
    page = anon.get(f"/wall/{decor['wall']}").get_data(as_text=True)
    assert "/static/uploads" not in page and "/media/" in page
    assert os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], decor["image"]))
    assert "static" not in app.config["UPLOAD_FOLDER"]


def test_photo_publique_visible_par_tous(anon, decor):
    r = anon.get("/media/" + decor["image"])
    assert r.status_code == 200 and "public" in r.headers["Cache-Control"] and r.mimetype == "image/jpeg"


def test_photo_privee_reservee_a_qui_a_acces(anon, alice, bob, prive):
    r = alice.get("/media/" + prive["image"])
    assert r.status_code == 200 and "private" in r.headers["Cache-Control"]
    assert anon.get("/media/" + prive["image"]).status_code == 404
    assert bob.get("/media/" + prive["image"]).status_code == 404


def test_photo_privee_visible_apres_deblocage(bob, prive):
    bob.post("/wall/%d/unlock" % prive["wall"], data={"code": prive["code"], "csrf_token": __import__("tests.helpers", fromlist=["csrf"]).csrf(bob)})
    assert bob.get("/media/" + prive["image"]).status_code == 200


def test_photo_dans_salle_privee_cachee(anon, alice, find):
    from tests.helpers import create_gym
    create_gym(alice, "Salle Privée", private=True)
    gym = find("gym", "Salle Privée")
    create_wall(alice, "Mur Dans Salle Privée", gym["id"])
    wall = find("wall", "Mur Dans Salle Privée")
    assert anon.get("/media/" + wall["image_filename"]).status_code == 404
    assert alice.get("/media/" + wall["image_filename"]).status_code == 200


def test_ancienne_adresse_static_uploads_introuvable(anon, prive):
    assert anon.get("/static/uploads/" + prive["image"]).status_code == 404


def test_noms_invalides_ou_inconnus_donnent_404(anon):
    assert anon.get("/media/..%2fapp.py").status_code == 404
    assert anon.get("/media/zzz.jpg").status_code == 404
    assert anon.get("/media/" + "a" * 32 + ".jpg").status_code == 404
    assert anon.get("/media/" + "A" * 32 + ".jpg").status_code == 404


def test_fichier_manquant_sur_le_disque_donne_404(anon, app, decor):
    os.remove(os.path.join(app.config["UPLOAD_FOLDER"], decor["image"]))
    assert anon.get("/media/" + decor["image"]).status_code == 404
