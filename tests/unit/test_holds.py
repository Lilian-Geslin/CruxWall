"""Tests de src/services/holds.py : validation des prises envoyées par l'éditeur de bloc."""
import pytest

from src.services.holds import parse_holds


def prise(**over):
    base = {"x": 0.1, "y": 0.2, "type": "start"}
    base.update(over)
    return base


def deux(**over):
    return [prise(**over), prise(x=0.5, y=0.6, type="top")]


def test_liste_valide():
    holds, error = parse_holds([prise(w=0.05, h=0.04), prise(x=0.9, y=0.9, type="foot")])
    assert error is None
    assert holds == [(0.1, 0.2, "start", 0.05, 0.04), (0.9, 0.9, "foot", None, None)]


def test_type_par_defaut_mid():
    holds, _ = parse_holds([{"x": 0, "y": 0}, {"x": 1, "y": 1}])
    assert [h[2] for h in holds] == ["mid", "mid"]


def test_bornes_incluses():
    assert parse_holds([{"x": 0, "y": 0}, {"x": 1, "y": 1}])[1] is None


@pytest.mark.parametrize("brut", [None, "x", {"x": 1}, 5])
def test_pas_une_liste(brut):
    assert parse_holds(brut) == (None, "Prises invalides.")


def test_moins_de_deux_prises():
    assert parse_holds([])[1] == "Un bloc doit avoir au moins 2 prises."
    assert parse_holds([prise()])[1] == "Un bloc doit avoir au moins 2 prises."


def test_trop_de_prises():
    holds, error = parse_holds([prise()] * 101)
    assert holds is None and "100" in error
    assert parse_holds([prise()] * 100)[1] is None


def test_element_non_dictionnaire():
    assert parse_holds([prise(), "x"]) == (None, "Prises invalides.")


@pytest.mark.parametrize("champ,valeur", [("x", -0.1), ("x", 1.1), ("y", -1), ("y", 2), ("x", "0.5"), ("y", None),
                                          ("x", True), ("x", float("nan"))])
def test_position_invalide(champ, valeur):
    assert parse_holds(deux(**{champ: valeur}))[1] == "Position de prise invalide."


def test_type_inconnu():
    assert parse_holds(deux(type="zzz"))[1] == "Type de prise invalide."


@pytest.mark.parametrize("champ,valeur", [("w", 0), ("w", -0.2), ("h", 1.5), ("w", "a"), ("h", True), ("h", float("inf"))])
def test_taille_invalide(champ, valeur):
    assert parse_holds(deux(**{champ: valeur}))[1] == "Taille de prise invalide."


def test_taille_limite_acceptee():
    assert parse_holds(deux(w=1, h=1))[1] is None
