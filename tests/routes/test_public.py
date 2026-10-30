"""Pages publiques : accueil, contrôle de santé /health, listes de murs et de salles."""
from tests.helpers import create_gym, create_wall


def test_accueil_affiche_murs_et_salles(anon, decor):
    page = anon.get("/").get_data(as_text=True)
    assert "Mur Public" in page and "Salle Publique" in page


def test_accueil_cache_les_murs_prives(anon, prive):
    assert "Mur Privé" not in anon.get("/").get_data(as_text=True)


def test_accueil_limite_a_12_murs(app, alice):
    create_gym(alice, "Grande Salle")
    for i in range(14):
        create_wall(alice, f"Mur numero {i:02d}", 1)
    page = alice.get("/").get_data(as_text=True)
    assert sum(1 for i in range(14) if f"Mur numero {i:02d}" in page) == 12


def test_health_ok(anon):
    r = anon.get("/health")
    assert r.status_code == 200 and r.get_data(as_text=True) == "ok"
    assert "no-store" in r.headers["Cache-Control"]


def test_health_503_si_base_inaccessible(anon, monkeypatch):
    def boum():
        raise RuntimeError("base absente")
    monkeypatch.setattr("src.routes.public.get_db", boum)
    r = anon.get("/health")
    assert r.status_code == 503 and r.get_data(as_text=True) == "erreur"


def test_liste_des_murs_cache_les_prives(anon, alice, decor, prive):
    page = anon.get("/walls").get_data(as_text=True)
    assert "Mur Public" in page and "Mur Privé" not in page
    assert "Mur Privé" in alice.get("/walls").get_data(as_text=True)


def test_liste_des_murs_vide_propose_creation_aux_connectes(anon, alice):
    assert "Aucun mur" in anon.get("/walls").get_data(as_text=True)
    assert "/wall/new" in alice.get("/walls").get_data(as_text=True)


def test_liste_des_salles_affiche_aussi_les_salles_privees(anon, alice):
    create_gym(alice, "Salle Cachée", private=True)
    page = anon.get("/gyms").get_data(as_text=True)
    assert "Salle Cachée" in page
