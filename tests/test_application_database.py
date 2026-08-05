from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import text

from services.application_database import (
    APPLICATION_SCHEMA_VERSION,
    ApplicationSchemaVersionModel,
    create_database_engine,
    dispose_database_engine,
    display_database_url,
    initialize_application_database,
    resolve_database_url,
)
from services.storage.database_storage import DatabaseStorageBackend
from services.storage.factory import create_storage_backend


def test_default_database_url_uses_one_application_database(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TemporaryDirectory() as directory:
        data_dir = Path(directory)
        assert resolve_database_url(data_dir) == (
            f"sqlite:///{(data_dir / 'chatgpt2api.db').resolve().as_posix()}"
        )


def test_postgresql_url_is_normalized_and_password_is_hidden(monkeypatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://tester:secret@example.test:5432/chatgpt2api",
    )
    resolved = resolve_database_url()
    assert resolved.startswith("postgresql+psycopg2://")
    assert "secret" not in display_database_url(resolved)
    assert "***" in display_database_url(resolved)


def test_unsupported_database_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported application database backend"):
        create_database_engine("mysql://example.invalid/chatgpt2api", shared=False)


def test_account_repository_always_uses_application_database(
    monkeypatch,
) -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        database_url = f"sqlite:///{(root / 'selected.db').as_posix()}"
        monkeypatch.setenv("DATABASE_URL", database_url)
        try:
            backend = create_storage_backend(root)
            assert isinstance(backend, DatabaseStorageBackend)
            assert backend.database_url == database_url
        finally:
            dispose_database_engine(database_url)


def test_sqlite_engine_is_shared_and_configured() -> None:
    with TemporaryDirectory() as directory:
        database_url = f"sqlite:///{(Path(directory) / 'app.db').as_posix()}"
        try:
            first = create_database_engine(database_url)
            second = create_database_engine(database_url)
            assert first is second

            with first.connect() as connection:
                assert connection.execute(text("PRAGMA foreign_keys")).scalar_one() == 1
                assert connection.execute(text("PRAGMA journal_mode")).scalar_one() == "wal"
                assert connection.execute(text("PRAGMA synchronous")).scalar_one() == 1
                assert connection.execute(text("PRAGMA busy_timeout")).scalar_one() >= 1000
        finally:
            dispose_database_engine(database_url)


def test_application_database_schema_is_initialized_once() -> None:
    with TemporaryDirectory() as directory:
        database_url = f"sqlite:///{(Path(directory) / 'app.db').as_posix()}"
        try:
            first = initialize_application_database(database_url)
            second = initialize_application_database(database_url)
            assert first is second
            with first.connect() as connection:
                assert connection.execute(
                    text("SELECT version FROM application_schema_version WHERE id = 1")
                ).scalar_one() == APPLICATION_SCHEMA_VERSION
        finally:
            dispose_database_engine(database_url)


def test_disposed_shared_engine_is_not_returned_from_cache() -> None:
    with TemporaryDirectory() as directory:
        database_url = f"sqlite:///{(Path(directory) / 'app.db').as_posix()}"
        first = create_database_engine(database_url)
        dispose_database_engine(database_url)
        try:
            assert create_database_engine(database_url) is not first
        finally:
            dispose_database_engine(database_url)


def test_application_database_rejects_unknown_schema_version() -> None:
    with TemporaryDirectory() as directory:
        database_url = f"sqlite:///{(Path(directory) / 'app.db').as_posix()}"
        try:
            engine = initialize_application_database(database_url)
            with engine.begin() as connection:
                connection.execute(
                    ApplicationSchemaVersionModel.__table__.update()
                    .where(ApplicationSchemaVersionModel.id == 1)
                    .values(version=APPLICATION_SCHEMA_VERSION + 1)
                )
            try:
                initialize_application_database(database_url)
            except RuntimeError as exc:
                assert "unsupported application database schema version" in str(exc)
            else:
                raise AssertionError("unknown schema version was accepted")
        finally:
            dispose_database_engine(database_url)
