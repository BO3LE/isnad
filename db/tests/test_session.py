"""Engines the platform builds keep a failed statement's values out of the exception text."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from db.models import Base, User
from db.session import make_engine, make_session_factory


def test_a_failed_insert_does_not_quote_the_values_it_was_given(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'gp.db'}")
    Base.metadata.create_all(engine)
    sessions = make_session_factory(engine)
    with sessions() as s:
        s.add(User(id=uuid.uuid4(), email="private.person@example.com"))
        s.commit()

    with sessions() as s, pytest.raises(IntegrityError) as failed:
        s.add(User(id=uuid.uuid4(), email="private.person@example.com"))
        s.commit()

    assert "private.person@example.com" not in str(failed.value)
    assert "hidden" in str(failed.value)  # SQLAlchemy says why the parameters are missing
