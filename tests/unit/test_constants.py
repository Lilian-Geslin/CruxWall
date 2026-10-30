"""Tests des constantes de référence (src/constants.py) : cohérence des listes, des quotas et des expressions régulières."""
import pytest

from src import constants as C


def test_cotations_ordonnees_et_uniques():
    assert len(C.GRADES) == len(set(C.GRADES)) == 41
    assert C.GRADES[0] == "3a" and C.GRADES[-1] == "9c"
    # l'ordre des listes sert à comparer les difficultés : 6a < 6a+ < 6b
    assert C.GRADES.index("6a") < C.GRADES.index("6a+") < C.GRADES.index("6b")
    # 9c est la dernière cotation : pas de « 9c+ »
    assert "9c+" not in C.GRADES


def test_quotas_bien_formes():
    assert set(C.QUOTAS) == {"wall", "gym", "block"}
    for kind, q in C.QUOTAS.items():
        assert q["table"] == kind
        assert q["daily"] <= q["total"]
        assert q["label"]


def test_limites_demandees():
    assert (C.QUOTAS["wall"]["total"], C.QUOTAS["wall"]["daily"]) == (250, 50)
    assert (C.QUOTAS["gym"]["total"], C.QUOTAS["gym"]["daily"]) == (100, 25)
    assert (C.QUOTAS["block"]["total"], C.QUOTAS["block"]["daily"]) == (500, 100)
    assert C.NAME_MAX == 100 and C.SEARCH_MAX == 100 and C.REGISTER_IP_MAX == 50
    assert (C.SUGGEST_WALLS_MAX, C.SUGGEST_BLOCKS_MAX) == (25, 50)


def test_types_de_prises_et_couleurs():
    assert C.HOLD_TYPES == {"start", "mid", "top", "foot"}
    assert C.DEFAULT_BLOCK_COLOR in C.ALLOWED_COLORS
    assert all(c.startswith("#") and len(c) == 7 for c in C.ALLOWED_COLORS)


def test_alphabet_des_codes_sans_caracteres_ambigus():
    assert len(C.ACCESS_CODE_ALPHABET) == 32
    assert not set("01IO") & set(C.ACCESS_CODE_ALPHABET)
    assert C.ACCESS_CODE_LENGTH == 10


@pytest.mark.parametrize("pseudo,valide", [("abc", True), ("Alice_01", True), ("a-b-c", True), ("ab", False),
                                           ("a" * 31, False), ("a b", False), ("é", False), ("a@b", False)])
def test_regex_pseudo(pseudo, valide):
    assert bool(C.PSEUDO_RE.match(pseudo)) is valide


@pytest.mark.parametrize("email,valide", [("a@b.fr", True), ("a.b+c@d.example.com", True), ("a@b", False),
                                          ("a b@c.fr", False), ("@b.fr", False), ("a@.fr", False)])
def test_regex_email(email, valide):
    assert bool(C.EMAIL_RE.match(email)) is valide


@pytest.mark.parametrize("nom,valide", [("a" * 31 + ".jpg", False), ("0123456789abcdef0123456789abcdef.jpg", True),
                                        ("0123456789ABCDEF0123456789abcdef.jpg", False), ("../x.jpg", False),
                                        ("0123456789abcdef0123456789abcdef.png", False)])
def test_regex_nom_de_photo(nom, valide):
    assert bool(C.MEDIA_NAME_RE.match(nom)) is valide


@pytest.mark.parametrize("ua,robot", [("Googlebot/2.1", True), ("curl/8.0", True), ("python-requests/2.31", True),
                                      ("UptimeRobot monitor", True), ("Mozilla/5.0 (iPhone) Safari", False)])
def test_regex_robots(ua, robot):
    assert bool(C.BOT_UA_RE.search(ua)) is robot


def test_motifs_de_signalement():
    assert set(C.REPORT_REASONS) == {"person", "inappropriate", "rights", "personal", "other"}
    assert set(C.REPORT_STATUS_LABELS) == {"open", "dismissed", "removed", "gone"}


def test_bornes_diverses():
    assert (C.PASSWORD_MIN, C.PASSWORD_MAX) == (8, 128)
    assert C.REGISTER_MIN_SECONDS < C.REGISTER_MAX_SECONDS
    assert C.MAX_FAVORITES == 200 and C.MAX_TODO == 500
    assert C.LOGIN_PAIR_MAX < C.LOGIN_IP_MAX < C.LOGIN_EMAIL_MAX
    assert C.SETTINGS_OK_MESSAGES.keys() == {"pseudo", "email", "password"}
