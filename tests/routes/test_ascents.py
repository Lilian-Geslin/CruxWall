"""Cotation communautaire (notes) et ascensions (fait / flash) + carnet persistant."""
import pytest

from tests.helpers import post, post_json


def url(decor, what):
    return f"/api/block/{decor['block']}/{what}"


class TestNotes:
    def test_enregistrement_puis_mise_a_jour(self, bob, decor, dbq):
        j = post_json(bob, url(decor, "note"), {"note": "6b"}).get_json()
        assert j["success"] and j["message"] == "Cotation enregistrée." and j["notes"] == [{"note": "6b", "user_name": "Bob"}]
        j = post_json(bob, url(decor, "note"), {"note": "6c"}).get_json()
        assert j["message"] == "Cotation mise à jour." and len(dbq("SELECT 1 FROM block_note")) == 1
        assert dbq("SELECT note FROM block_note")[0][0] == "6c"

    def test_un_vote_par_compte(self, alice, bob, decor, dbq):
        post_json(alice, url(decor, "note"), {"note": "6a"}); post_json(bob, url(decor, "note"), {"note": "6b"})
        assert len(dbq("SELECT 1 FROM block_note")) == 2

    @pytest.mark.parametrize("payload,status", [({"note": ""}, 400), ({"note": "9z"}, 400), ({}, 400)])
    def test_refus(self, bob, decor, payload, status):
        assert post_json(bob, url(decor, "note"), payload).status_code == status

    def test_corps_invalide(self, bob, decor):
        assert bob.post(url(decor, "note"), data="x", headers={"X-CSRF-Token": "x"}).status_code == 400

    def test_bloc_inexistant(self, bob):
        assert post_json(bob, "/api/block/999/note", {"note": "6a"}).status_code == 404

    def test_exige_connexion_et_csrf(self, anon, bob, decor):
        assert anon.post(url(decor, "note"), json={"note": "6a"}).status_code in (400, 401, 302)
        assert bob.post(url(decor, "note"), json={"note": "6a"}).status_code == 400

    def test_mur_prive_ferme(self, bob, prive):
        assert post_json(bob, f"/api/block/{prive['block']}/note", {"note": "6a"}).status_code == 404

    def test_lecture(self, anon, bob, decor):
        post_json(bob, url(decor, "note"), {"note": "6b"})
        j = anon.get(url(decor, "notes")).get_json()
        assert j["notes"][0]["note"] == "6b" and j["my_note"] is None
        assert bob.get(url(decor, "notes")).get_json()["my_note"] == "6b"

    def test_lecture_mur_prive(self, anon, prive):
        assert anon.get(f"/api/block/{prive['block']}/notes").status_code == 404

    def test_toutes_les_cotations_valides_acceptees(self, bob, decor):
        from src.constants import GRADES
        for g in GRADES:
            assert post_json(bob, url(decor, "note"), {"note": g}).status_code == 200, g


class TestAscensions:
    def test_fait(self, bob, decor, dbq):
        j = post_json(bob, url(decor, "ascent"), {"done": True}).get_json()
        assert j["my_ascent"] == {"done": 1, "flash": 0} and j["ascents"][0]["user_name"] == "Bob"
        assert dbq("SELECT done_at FROM ascent")[0][0] is not None

    def test_flash_implique_fait(self, bob, decor):
        assert post_json(bob, url(decor, "ascent"), {"flash": True}).get_json()["my_ascent"] == {"done": 1, "flash": 1}

    def test_decocher(self, bob, decor):
        post_json(bob, url(decor, "ascent"), {"done": True})
        j = post_json(bob, url(decor, "ascent"), {}).get_json()
        assert j["my_ascent"] == {"done": 0, "flash": 0} and j["ascents"] == []

    def test_done_at_conserve_si_deja_fait(self, bob, decor, dbq, dbq_write):
        post_json(bob, url(decor, "ascent"), {"done": True})
        dbq_write("UPDATE ascent SET done_at = '2024-05-05 10:00:00'")
        post_json(bob, url(decor, "ascent"), {"flash": True})
        assert dbq("SELECT done_at FROM ascent")[0][0] == "2024-05-05 10:00:00"

    def test_une_ligne_par_compte_et_bloc(self, bob, decor, dbq):
        for _ in range(3):
            post_json(bob, url(decor, "ascent"), {"done": True})
        assert len(dbq("SELECT 1 FROM ascent")) == 1

    def test_flash_en_tete_de_liste(self, alice, bob, decor):
        post_json(alice, url(decor, "ascent"), {"done": True}); post_json(bob, url(decor, "ascent"), {"flash": True})
        names = [a["user_name"] for a in alice.get(url(decor, "ascents")).get_json()["ascents"]]
        assert names == ["Bob", "Alice"]

    def test_un_bloc_reussi_sort_de_la_liste_a_faire(self, bob, decor, dbq):
        post(bob, f"/block/{decor['block']}/todo")
        assert dbq("SELECT 1 FROM block_todo")
        post_json(bob, url(decor, "ascent"), {"done": True})
        assert dbq("SELECT 1 FROM block_todo") == []

    def test_carnet_alimente(self, bob, decor, dbq):
        post_json(bob, url(decor, "ascent"), {"flash": True})
        r = dbq("SELECT * FROM climb_log")[0]
        assert (r["block_name"], r["wall_name"], r["flash"], r["grade"]) == ("Bloc Public", "Mur Public", 1, "6a")

    def test_decocher_retire_du_carnet(self, bob, decor, dbq):
        post_json(bob, url(decor, "ascent"), {"done": True}); post_json(bob, url(decor, "ascent"), {})
        assert dbq("SELECT 1 FROM climb_log") == []

    def test_refus(self, bob, anon, decor):
        assert post_json(bob, "/api/block/999/ascent", {"done": True}).status_code == 404
        assert bob.post(url(decor, "ascent"), data="x", headers={"X-CSRF-Token": "x"}).status_code == 400
        assert anon.post(url(decor, "ascent"), json={"done": True}).status_code in (400, 401, 302)

    def test_mur_prive_ferme(self, bob, prive):
        assert post_json(bob, f"/api/block/{prive['block']}/ascent", {"done": True}).status_code == 404

    def test_lecture_anonyme(self, anon, bob, decor):
        post_json(bob, url(decor, "ascent"), {"done": True})
        j = anon.get(url(decor, "ascents")).get_json()
        assert j["my_ascent"] == {"done": 0, "flash": 0} and len(j["ascents"]) == 1
        assert anon.get("/api/block/999/ascents").status_code == 404

    def test_lecture_mur_prive(self, anon, prive):
        assert anon.get(f"/api/block/{prive['block']}/ascents").status_code == 404
