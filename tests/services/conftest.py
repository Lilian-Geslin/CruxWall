"""Fixtures propres aux tests des services : contexte de requête connecté, fabriques de salles / murs / blocs en base."""
from contextlib import contextmanager

import pytest
from flask import session


@pytest.fixture
def as_user(app):
    """Contexte de requête dans lequel `session` contient le compte voulu : `with as_user(uid, 'admin'): ...`.

    Les services lisent flask.session et flask.request ; hors d'une requête, ils lèvent une erreur.
    """
    @contextmanager
    def ctx(user_id=None, role="user", name="Test", **request_kwargs):
        with app.test_request_context(**request_kwargs):
            if user_id is not None:
                session["user_id"] = user_id
                session["user_role"] = role
                session["user_name"] = name
            yield
    return ctx


@pytest.fixture
def add_gym(conn):
    def make(name="Salle", created_by=None, private=False, code=None):
        cur = conn.execute("INSERT INTO gym(name, location, created_by, is_private, access_code) VALUES(?,?,?,?,?)",
                           (name, "Marseille", created_by, 1 if private else 0, code))
        conn.commit()
        return cur.lastrowid
    return make


@pytest.fixture
def add_wall(conn):
    def make(name="Mur", created_by=None, gym_id=None, private=False, image="mur.jpg", code=None):
        cur = conn.execute(
            "INSERT INTO wall(gym_id, name, image_filename, created_by, is_private, access_code, last_activity_at) "
            "VALUES(?,?,?,?,?,?, CURRENT_TIMESTAMP)",
            (gym_id, name, image, created_by, 1 if private else 0, code))
        conn.commit()
        return cur.lastrowid
    return make


@pytest.fixture
def add_block(conn):
    def make(wall_id, name="Bloc", grade="6a", created_by=None, holds=2):
        cur = conn.execute("INSERT INTO block(wall_id, name, grade, color, created_by) VALUES(?,?,?,?,?)",
                           (wall_id, name, grade, "#3b82f6", created_by))
        block_id = cur.lastrowid
        for i in range(holds):
            conn.execute("INSERT INTO hold(block_id, x, y, hold_type) VALUES(?,?,?,?)", (block_id, 0.1 * (i + 1), 0.2, "mid"))
        conn.commit()
        return block_id
    return make


@pytest.fixture
def scalar(conn):
    """scalar('SELECT COUNT(*) ...', params) -> première colonne de la première ligne."""
    return lambda sql, *params: conn.execute(sql, params).fetchone()[0]
