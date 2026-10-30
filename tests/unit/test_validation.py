"""Tests de src/services/validation.py : nettoyage des textes, liens, nombres et adresses de redirection."""
import pytest

from src.services.validation import (clean_link, clean_text, normalize_email, safe_next_url, safe_referrer, to_float,
                                     to_int)


class TestCleanText:
    def test_non_chaine(self):
        assert clean_text(None) == "" and clean_text(5) == "" and clean_text(["a"]) == ""

    def test_retire_les_caracteres_de_controle(self):
        assert clean_text("a\x00b\x07c\x7fd\x0be") == "abcde"

    def test_une_ligne_remplace_les_retours(self):
        assert clean_text("a\nb\r\nc\td") == "a b  c d"

    def test_multiligne_garde_les_retours(self):
        assert clean_text("  a\nb\n ", multiline=True) == "a\nb"

    def test_espaces_de_bord(self):
        assert clean_text("   salut  ") == "salut"


class TestCleanLink:
    def test_vide(self):
        assert clean_link("") == ("", None)
        assert clean_link(None) == ("", None)
        assert clean_link("   ") == ("", None)

    def test_ajoute_https(self):
        assert clean_link("youtube.com/watch?v=abc") == ("https://youtube.com/watch?v=abc", None)

    def test_garde_le_schema(self):
        assert clean_link("http://exemple.fr/x") == ("http://exemple.fr/x", None)
        assert clean_link("https://exemple.fr") == ("https://exemple.fr", None)

    @pytest.mark.parametrize("lien", ["javascript:alert(1)", "data:text/html,x", "ftp://a.fr/x", "file:///etc/passwd",
                                      "http://", "https://localhost", "mailto:a@b.fr"])
    def test_schemas_et_hotes_refuses(self, lien):
        value, error = clean_link(lien)
        assert value == "" and error and "invalide" in error

    def test_espace_refuse(self):
        assert clean_link("a b.com")[1] == "Le lien ne doit pas contenir d'espace."

    def test_trop_long(self):
        value, error = clean_link("https://exemple.fr/" + "a" * 300)
        assert value == "" and "300" in error

    def test_longueur_limite_acceptee(self):
        lien = "https://e.fr/" + "a" * (300 - len("https://e.fr/"))
        assert clean_link(lien) == (lien, None)


def test_normalize_email():
    assert normalize_email("  Alice@Exemple.FR ") == "alice@exemple.fr"
    assert normalize_email(None) == "" and normalize_email(12) == ""


@pytest.mark.parametrize("valeur,attendu", [(True, None), (False, None), ("12", 12), (" 7 ", 7), ("x", None), (None, None),
                                            (3.9, 3), ("3.7", None), ([], None)])
def test_to_int(valeur, attendu):
    assert to_int(valeur) == attendu


@pytest.mark.parametrize("valeur,attendu", [(True, None), ("1.0", None), (None, None), (1, 1.0), (0.25, 0.25),
                                            (float("nan"), None), (float("inf"), None), (float("-inf"), None)])
def test_to_float(valeur, attendu):
    assert to_float(valeur) == attendu


class TestSafeNextUrl:
    @pytest.mark.parametrize("cible", ["/wall/3", "/", "/a/b?x=1&y=2", "/block/4#haut"])
    def test_chemins_internes(self, cible):
        assert safe_next_url(cible) == cible

    @pytest.mark.parametrize("cible", ["https://evil.com", "//evil.com", "/\\evil.com", "evil.com", "javascript:alert(1)",
                                       "/a\nb", "/a\x00b", "", None, 42])
    def test_cibles_refusees(self, cible):
        assert safe_next_url(cible) == "/"

    def test_valeur_par_defaut(self):
        assert safe_next_url("//evil.com", default="/login") == "/login"

    def test_espaces_retires(self):
        assert safe_next_url("  /x ") == "/x"


class TestSafeReferrer:
    def test_meme_site(self, app):
        with app.test_request_context(headers={"Referer": "http://localhost/wall/3?x=1"}):
            assert safe_referrer() == "/wall/3?x=1"

    def test_autre_site(self, app):
        with app.test_request_context(headers={"Referer": "http://evil.com/wall/3"}):
            assert safe_referrer("/accueil") == "/accueil"

    def test_sans_referer(self, app):
        with app.test_request_context():
            assert safe_referrer() == "/"

    def test_chemin_double_slash_refuse(self, app):
        with app.test_request_context(headers={"Referer": "http://localhost//evil.com"}):
            assert safe_referrer() == "/"
