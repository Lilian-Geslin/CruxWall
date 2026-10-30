"""Fixtures propres aux tests de routes : petits décors (salle, murs, blocs) prêts à l'emploi."""
import pytest

from tests.helpers import create_block, create_gym, create_wall


@pytest.fixture
def find(dbq):
    """find('wall', 'Mon mur') -> ligne de la table (id, image_filename…), None si absente."""
    def _find(table, name):
        rows = dbq(f"SELECT * FROM {table} WHERE name = ?", name)
        return rows[0] if rows else None
    return _find


@pytest.fixture
def decor(app, alice, bob, find):
    """Alice possède une salle publique avec un mur public et un bloc ; Bob n'a rien."""
    create_gym(alice, "Salle Publique")
    gym = find("gym", "Salle Publique")
    create_wall(alice, "Mur Public", gym["id"])
    wall = find("wall", "Mur Public")
    block_id = create_block(alice, wall["id"], "Bloc Public").get_json()["block_id"]
    return {"gym": gym["id"], "wall": wall["id"], "image": wall["image_filename"], "block": block_id}


@pytest.fixture
def prive(app, alice, find):
    """Alice possède un mur privé (code d'accès) avec un bloc."""
    create_gym(alice, "Salle Ouverte")
    create_wall(alice, "Mur Privé", find("gym", "Salle Ouverte")["id"], private=True)
    wall = find("wall", "Mur Privé")
    block_id = create_block(alice, wall["id"], "Bloc Secret").get_json()["block_id"]
    return {"wall": wall["id"], "image": wall["image_filename"], "code": wall["access_code"], "block": block_id}
