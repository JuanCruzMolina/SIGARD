"""Control-flow safety checks only; never connect to PostgreSQL or Docker."""

from unittest.mock import MagicMock

import pytest

import postgis_support as support


def test_wrong_cluster_identity_cannot_reset_even_under_optimized_python(monkeypatch):
    monkeypatch.setenv("SIGARD_POSTGIS_RUN_ID", "sigard-disposable-" + "a" * 16)
    engine = MagicMock()
    engine.url = f"postgresql+psycopg2://{support.USER}@127.0.0.1:{support.PORT}/{support.SCHEMA_DB}"
    connection = engine.begin.return_value.__enter__.return_value
    connection.scalar.return_value = "different-cluster"
    with pytest.raises(ValueError, match="reset forbidden"):
        support.reset_schema(engine)
    connection.execute.assert_not_called()


def test_invalid_destination_is_rejected_before_creating_an_engine(monkeypatch):
    engine_factory = MagicMock(side_effect=AssertionError("Must not connect"))
    monkeypatch.setattr(support, "create_engine", engine_factory)
    with pytest.raises(ValueError, match="explicit disposable"):
        support.checked_engine(f"postgresql+psycopg2://{support.USER}@127.0.0.1:5432/{support.SCHEMA_DB}")
    engine_factory.assert_not_called()
