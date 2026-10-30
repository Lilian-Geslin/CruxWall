"""Favoris (murs, salles, blocs), liste « à faire » et carnet de progression."""
import pytest

from tests.helpers import create_block, create_gym, create_wall, post, post_json


class TestBascule:
    @pytest.mark.parametrize("kind,table", [("wall", "wall_favorite"), ("gym", "gym_favorite"), ("block", "block_favorite")])
    def test_ajout_puis_retrait(self, bob, decor, dbq, kind, table):
        path = f"/{kind}/{decor[kind]}/favorite"
        assert post(bob, path).status_code == 302 and len(dbq(f"SELECT 1 FROM {table}")) == 1
        post(bob, path)
        assert dbq(f"SELECT 1 FROM {table}") == []

    def test_todo(self, bob, decor, dbq):
        post(bob, f"/block/{decor['block']}/todo")
        assert len(dbq("SELECT 1 FROM block_todo")) == 1
        post(bob, f"/block/{decor['block']}/todo")
        assert dbq("SELECT 1 FROM block_todo") == []

    def test_redirection_vers_la_page_d_origine(self, bob, decor):
        r = post(bob, f"/wall/{decor['wall']}/favorite", headers={"Referer": "http://localhost/gym/1"})
        assert r.headers["Location"].endswith("/gym/1")

    def test_redirection_externe_ignoree(self, bob, decor):
        r = post(bob, f"/wall/{decor['wall']}/favorite", headers={"Referer": "https://evil.example/x"})
        assert r.headers["Location"] == f"/wall/{decor['wall']}"

    def test_exige_connexion_csrf_et_post(self, anon, bob, decor):
        assert anon.post(f"/wall/{decor['wall']}/favorite").status_code == 400
        assert bob.post(f"/wall/{decor['wall']}/favorite").status_code == 400
        assert bob.get(f"/wall/{decor['wall']}/favorite").status_code == 405

    def test_inexistants(self, bob):
        for p in ["/wall/99/favorite", "/gym/99/favorite", "/block/99/favorite", "/block/99/todo"]:
            assert post(bob, p).status_code == 404, p

    def test_mur_prive_introuvable(self, bob, prive):
        assert post(bob, f"/wall/{prive['wall']}/favorite").status_code == 404
        assert post(bob, f"/block/{prive['block']}/favorite").status_code == 404
        assert post(bob, f"/block/{prive['block']}/todo").status_code == 404

    @pytest.mark.parametrize("path_fn,label", [
        (lambda d: f"/wall/{d['wall']}/favorite", "murs favoris"),
        (lambda d: f"/gym/{d['gym']}/favorite", "salles favorites"),
        (lambda d: f"/block/{d['block']}/favorite", "blocs favoris"),
        (lambda d: f"/block/{d['block']}/todo", "« à faire »"),
    ])
    def test_limites(self, bob, decor, monkeypatch, path_fn, label):
        for name in ["MAX_FAVORITES", "MAX_TODO"]:
            monkeypatch.setattr(f"src.routes.favorites.{name}", 0)
        r = post(bob, path_fn(decor))
        assert r.status_code == 400 and "Limite atteinte" in r.get_data(as_text=True) and label in r.get_data(as_text=True)

    def test_retirer_reste_possible_a_la_limite(self, bob, decor, monkeypatch, dbq):
        monkeypatch.setattr("src.routes.favorites.MAX_FAVORITES", 1)
        post(bob, f"/wall/{decor['wall']}/favorite")
        assert post(bob, f"/wall/{decor['wall']}/favorite").status_code == 302 and dbq("SELECT 1 FROM wall_favorite") == []

    def test_les_listes_sont_par_compte(self, alice, bob, decor, dbq):
        post(alice, f"/wall/{decor['wall']}/favorite"); post(bob, f"/wall/{decor['wall']}/favorite")
        assert len(dbq("SELECT 1 FROM wall_favorite")) == 2


class TestPages:
    def test_exigent_connexion(self, anon):
        for p in ["/favoris", "/a-faire", "/carnet"]:
            assert anon.get(p).status_code == 302

    def test_favoris(self, bob, decor):
        for kind in ("wall", "gym", "block"):
            post(bob, f"/{kind}/{decor[kind]}/favorite")
        page = bob.get("/favoris").get_data(as_text=True)
        assert "Mur Public" in page and "Salle Publique" in page and "Bloc Public" in page

    def test_favoris_masque_un_mur_devenu_prive(self, alice, bob, decor):
        post(bob, f"/wall/{decor['wall']}/favorite"); post(bob, f"/block/{decor['block']}/favorite")
        post(alice, f"/wall/{decor['wall']}/edit", {"name": "Mur Public", "gym_id": decor["gym"], "is_private": "1"})
        page = bob.get("/favoris").get_data(as_text=True)
        assert "Mur Public" not in page and "Bloc Public" not in page

    def test_a_faire(self, bob, decor):
        post(bob, f"/block/{decor['block']}/todo")
        assert "Bloc Public" in bob.get("/a-faire").get_data(as_text=True)

    def test_a_faire_vide(self, bob):
        assert bob.get("/a-faire").status_code == 200

    def test_a_faire_masque_un_mur_devenu_prive(self, alice, bob, decor):
        post(bob, f"/block/{decor['block']}/todo")
        post(alice, f"/wall/{decor['wall']}/edit", {"name": "Mur Public", "gym_id": decor["gym"], "is_private": "1"})
        assert "Bloc Public" not in bob.get("/a-faire").get_data(as_text=True)


class TestCarnet:
    def test_carnet_vide(self, bob):
        assert bob.get("/carnet").status_code == 200

    def test_statistiques(self, alice, bob, decor, find):
        create_wall(alice, "Mur 2", decor["gym"])
        w2 = find("wall", "Mur 2")["id"]
        b2 = create_block(alice, w2, "Dur", grade="7a").get_json()["block_id"]
        post_json(bob, f"/api/block/{decor['block']}/ascent", {"done": True})
        post_json(bob, f"/api/block/{b2}/ascent", {"flash": True})
        page = bob.get("/carnet").get_data(as_text=True)
        assert "Bloc Public" in page and "Dur" in page and "7a" in page

    def test_le_carnet_survit_a_la_suppression_du_bloc(self, alice, bob, decor):
        post_json(bob, f"/api/block/{decor['block']}/ascent", {"done": True})
        post(alice, f"/block/{decor['block']}/delete")
        page = bob.get("/carnet").get_data(as_text=True)
        assert "Bloc Public" in page and f"/block/{decor['block']}" not in page      # visible mais plus cliquable

    def test_le_carnet_survit_a_la_suppression_de_la_salle(self, alice, bob, decor):
        post_json(bob, f"/api/block/{decor['block']}/ascent", {"flash": True})
        post(alice, f"/gym/{decor['gym']}/delete")
        assert "Bloc Public" in bob.get("/carnet").get_data(as_text=True)

    def test_le_carnet_est_personnel(self, alice, bob, decor):
        post_json(bob, f"/api/block/{decor['block']}/ascent", {"done": True})
        assert "Bloc Public" not in alice.get("/carnet").get_data(as_text=True)

    def test_bloc_d_un_mur_devenu_prive_non_cliquable(self, alice, bob, decor):
        post_json(bob, f"/api/block/{decor['block']}/ascent", {"done": True})
        post(alice, f"/wall/{decor['wall']}/edit", {"name": "Mur Public", "gym_id": decor["gym"], "is_private": "1"})
        page = bob.get("/carnet").get_data(as_text=True)
        assert f'href="/block/{decor["block"]}"' not in page
