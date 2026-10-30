"""Recherche globale /search (barre du haut) : murs et salles, caractères % et _ littéraux, droits d'accès."""
from tests.helpers import create_gym, create_wall


def noms(client, q):
    return sorted(x["name"] for x in client.get("/search", query_string={"q": q}).get_json())


def test_recherche_normale_trouve_murs_et_salles(alice, decor):
    resultats = alice.get("/search?q=publi").get_json()
    types = {(x["type"], x["name"]) for x in resultats}
    assert ("wall", "Mur Public") in types and ("gym", "Salle Publique") in types


def test_un_seul_caractere_ne_donne_rien(alice, decor):
    assert alice.get("/search?q=g").get_json() == [] and alice.get("/search").get_json() == []


def test_underscore_et_pourcent_sont_des_caracteres_ordinaires(alice):
    for nom in ("Gym_A", "GymXA", "100%Grimpe", "100abGrimpe"):
        create_gym(alice, nom)
    assert noms(alice, "m_A") == ["Gym_A"]
    assert noms(alice, "100%G") == ["100%Grimpe"]
    assert alice.get("/search?q=%25%25").get_json() == []


def test_tres_long_texte_accepte_sans_erreur(alice):
    assert alice.get("/search?q=" + "a" * 5000).status_code == 200


def test_mur_prive_absent_pour_un_etranger(anon, alice, bob, prive):
    assert noms(anon, "Privé") == [] and noms(bob, "Privé") == []
    assert noms(alice, "Privé") == ["Mur Privé"]


def test_salle_privee_toujours_listee_mais_marquee(anon, alice):
    create_gym(alice, "Salle Cachée", private=True)
    item = [x for x in anon.get("/search?q=Cach").get_json() if x["type"] == "gym"][0]
    assert item["is_private"] is True and item["can_view"] is False
    item = [x for x in alice.get("/search?q=Cach").get_json() if x["type"] == "gym"][0]
    assert item["can_view"] is True


def test_resultats_limites_a_12(alice):
    for i in range(15):
        create_gym(alice, f"Salle test {i:02d}")
    assert len(alice.get("/search?q=Salle test").get_json()) == 10   # 10 salles au maximum


def test_mur_dans_salle_privee_cache(anon, alice, find):
    create_gym(alice, "Salle P", private=True)
    create_wall(alice, "Mur de la salle P", find("gym", "Salle P")["id"])
    assert noms(anon, "Mur de la") == []
