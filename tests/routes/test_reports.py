"""Signalements de murs et de blocs."""
import pytest

from src import constants as C
from tests.helpers import create_block, post


def report(client, kind, target, reason="inappropriate", **extra):
    return post(client, "/report", {"target_type": kind, "target_id": str(target), "reason": reason, **extra})


class TestSignalement:
    def test_signaler_un_mur(self, bob, decor, dbq):
        r = report(bob, "wall", decor["wall"], details="  photo gênante ")
        assert r.status_code == 200 and "Merci" in r.get_data(as_text=True)
        row = dbq("SELECT * FROM report")[0]
        assert (row["target_type"], row["target_id"], row["target_name"], row["wall_id"], row["reason"], row["details"], row["status"]) == \
            ("wall", decor["wall"], "Mur Public", decor["wall"], "inappropriate", "photo gênante", "open")

    def test_signaler_un_bloc(self, bob, decor, dbq):
        assert report(bob, "block", decor["block"], "person").status_code == 200
        assert dbq("SELECT target_name FROM report")[0][0] == "Bloc Public"

    @pytest.mark.parametrize("kind,target,reason,extra", [
        ("autre", 1, "person", {}), ("wall", "", "person", {}), ("wall", 1, "inconnu", {}), ("wall", 1, "", {}),
        ("wall", 1, "other", {}), ("wall", 1, "other", {"details": "abc"}), ("wall", 1, "person", {"details": "d" * 501}),
    ])
    def test_refus_400(self, bob, decor, kind, target, reason, extra):
        assert report(bob, kind, target, reason, **extra).status_code == 400

    def test_motif_autre_avec_precision(self, bob, decor):
        assert report(bob, "wall", decor["wall"], "other", details="Texte explicatif").status_code == 200

    def test_cible_inexistante(self, bob):
        assert report(bob, "wall", 99).status_code == 404
        assert report(bob, "block", 99).status_code == 404

    def test_mur_prive_introuvable(self, bob, prive):
        assert report(bob, "wall", prive["wall"]).status_code in (403, 404)
        assert report(bob, "block", prive["block"]).status_code in (403, 404)

    def test_mur_prive_signalable_apres_code(self, bob, prive, dbq):
        post(bob, f"/wall/{prive['wall']}/unlock", {"code": prive["code"]})
        assert report(bob, "wall", prive["wall"]).status_code == 200

    def test_doublon_en_attente(self, bob, decor, dbq):
        report(bob, "wall", decor["wall"])
        r = report(bob, "wall", decor["wall"], "person")
        assert "Déjà signalé" in r.get_data(as_text=True) and len(dbq("SELECT 1 FROM report")) == 1

    def test_deux_comptes_peuvent_signaler_le_meme_contenu(self, alice, bob, decor, dbq):
        report(alice, "wall", decor["wall"]); report(bob, "wall", decor["wall"])
        assert len(dbq("SELECT 1 FROM report")) == 2

    def test_limite_par_compte(self, bob, alice, decor, find, dbq):
        from tests.helpers import create_wall
        for i in range(C.REPORT_USER_MAX):
            create_wall(alice, f"M{i}", decor["gym"])
            assert report(bob, "wall", find("wall", f"M{i}")["id"]).status_code == 200
        create_wall(alice, "M-de-trop", decor["gym"])
        r = report(bob, "wall", find("wall", "M-de-trop")["id"])
        assert r.status_code == 429 and "Trop de signalements" in r.get_data(as_text=True)
        assert len(dbq("SELECT 1 FROM report")) == C.REPORT_USER_MAX

    def test_limite_par_ip(self, app, alice, decor, monkeypatch, dbq):
        monkeypatch.setattr("src.routes.reports.REPORT_IP_MAX", 1)
        from tests.helpers import register
        c1 = register(app, "Carla", "c1@example.fr")[0]; c2 = register(app, "Damien", "c2@example.fr")[0]
        assert report(c1, "wall", decor["wall"]).status_code == 200
        assert report(c2, "wall", decor["wall"]).status_code == 429

    def test_notifie_les_admins(self, bob, admin, decor, dbq):
        report(bob, "wall", decor["wall"])
        n = dbq("SELECT * FROM notification")
        assert len(n) == 1 and "Nouveau signalement" in n[0]["message"] and "Mur Public" in n[0]["message"]

    def test_exige_connexion_csrf_et_post(self, anon, bob, decor):
        assert anon.post("/report", data={}).status_code == 400
        assert bob.get("/report").status_code == 405

    def test_lien_de_retour_interne(self, bob, decor):
        r = report(bob, "wall", decor["wall"])
        assert f'href="/wall/{decor["wall"]}"' in r.get_data(as_text=True)

    def test_la_page_propose_le_formulaire(self, bob, decor):
        page = bob.get(f"/wall/{decor['wall']}").get_data(as_text=True)
        assert 'action="/report"' in page
