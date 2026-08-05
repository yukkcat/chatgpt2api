from __future__ import annotations

import json
from typing import Any, Sequence

from sqlalchemy import Column, Integer, String, Text, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from services.application_database import (
    DatabaseBase,
    display_database_url,
    initialize_application_database,
)
from services.storage.base import (
    StorageBackend,
    StorageCapabilities,
    StorageCollection,
    StorageMutation,
    StorageMutationResult,
    StorageRevisionConflictError,
    StorageSnapshot,
)
from services.storage.mutation import item_key, normalize_items, normalize_mutation


class AccountModel(DatabaseBase):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    access_token = Column(String(2048), unique=True, nullable=False, index=True)
    data = Column(Text, nullable=False)


class AuthKeyModel(DatabaseBase):
    __tablename__ = "auth_keys"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key_id = Column(String(255), unique=True, nullable=False, index=True)
    data = Column(Text, nullable=False)


class StorageRevisionModel(DatabaseBase):
    __tablename__ = "storage_revisions"

    collection = Column(String(32), primary_key=True)
    version = Column(Integer, nullable=False, default=0)


class DatabaseStorageBackend(StorageBackend):
    """Transactional database adapter with collection-level CAS revisions."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = initialize_application_database(database_url)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self._ensure_revision_rows()

    @staticmethod
    def _spec(collection: StorageCollection) -> tuple[type[Any], str]:
        if collection == "accounts":
            return AccountModel, "access_token"
        return AuthKeyModel, "key_id"

    @staticmethod
    def _serialize(item: dict[str, Any]) -> str:
        return json.dumps(
            item,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _deserialize(value: str) -> dict[str, Any] | None:
        try:
            item = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return None
        return item if isinstance(item, dict) else None

    def _ensure_revision_rows(self) -> None:
        for collection in ("accounts", "auth_keys"):
            session = self.Session()
            try:
                if session.get(StorageRevisionModel, collection) is None:
                    session.add(StorageRevisionModel(collection=collection, version=0))
                    session.commit()
            except IntegrityError:
                # Another process initialized the same row first.
                session.rollback()
            finally:
                session.close()

    def _begin_write(self, session: Any) -> None:
        if self.engine.dialect.name == "sqlite":
            # SQLite ignores SELECT FOR UPDATE. BEGIN IMMEDIATE serializes writers
            # before the revision is checked, preserving CAS semantics.
            session.execute(text("BEGIN IMMEDIATE"))

    @staticmethod
    def _check_revision(
        collection: StorageCollection,
        expected_revision: str | None,
        actual_revision: str,
    ) -> None:
        if expected_revision is not None and expected_revision != actual_revision:
            raise StorageRevisionConflictError(
                collection,
                expected_revision,
                actual_revision,
            )

    @staticmethod
    def _revision_value(collection: StorageCollection, version: int) -> str:
        return f"{collection}:{version}"

    def _locked_revision(self, session: Any, collection: StorageCollection) -> Any:
        return (
            session.query(StorageRevisionModel)
            .filter(StorageRevisionModel.collection == collection)
            .with_for_update()
            .one()
        )

    def _load_snapshot(self, collection: StorageCollection) -> StorageSnapshot:
        model, _ = self._spec(collection)
        for _ in range(3):
            session = self.Session()
            try:
                before = session.execute(
                    select(StorageRevisionModel.version).where(
                        StorageRevisionModel.collection == collection
                    )
                ).scalar_one()
                rows = session.query(model).order_by(model.id.asc()).all()
                items = [
                    item
                    for row in rows
                    if (item := self._deserialize(row.data)) is not None
                ]
                after = session.execute(
                    select(StorageRevisionModel.version)
                    .where(StorageRevisionModel.collection == collection)
                    .execution_options(populate_existing=True)
                ).scalar_one()
                if before == after:
                    return StorageSnapshot(
                        items=items,
                        revision=self._revision_value(collection, after),
                    )
            finally:
                session.close()
        raise RuntimeError(f"{collection} changed repeatedly while loading its snapshot")

    def load_accounts_snapshot(self) -> StorageSnapshot:
        return self._load_snapshot("accounts")

    def load_auth_keys_snapshot(self) -> StorageSnapshot:
        return self._load_snapshot("auth_keys")

    def _replace(
        self,
        collection: StorageCollection,
        items: Sequence[dict[str, Any]],
        *,
        expected_revision: str | None,
    ) -> StorageMutationResult:
        desired_items = normalize_items(collection, items)
        desired = {item_key(collection, item): item for item in desired_items}
        model, model_key = self._spec(collection)

        session = self.Session()
        try:
            self._begin_write(session)
            revision_row = self._locked_revision(session, collection)
            current_revision = self._revision_value(collection, revision_row.version)
            self._check_revision(collection, expected_revision, current_revision)

            rows = session.query(model).order_by(model.id.asc()).all()
            existing = {str(getattr(row, model_key)): row for row in rows}
            inserted = 0
            updated = 0
            deleted = 0

            for key in existing.keys() - desired.keys():
                session.delete(existing[key])
                deleted += 1

            for key, item in desired.items():
                serialized = self._serialize(item)
                row = existing.get(key)
                if row is None:
                    session.add(model(**{model_key: key}, data=serialized))
                    inserted += 1
                elif self._deserialize(row.data) != item:
                    row.data = serialized
                    updated += 1

            if inserted or updated or deleted:
                revision_row.version += 1
            session.commit()
            return StorageMutationResult(
                revision=self._revision_value(collection, revision_row.version),
                inserted=inserted,
                updated=updated,
                deleted=deleted,
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def replace_accounts(
        self,
        accounts: Sequence[dict[str, Any]],
        *,
        expected_revision: str | None = None,
    ) -> StorageMutationResult:
        return self._replace(
            "accounts",
            accounts,
            expected_revision=expected_revision,
        )

    def replace_auth_keys(
        self,
        auth_keys: Sequence[dict[str, Any]],
        *,
        expected_revision: str | None = None,
    ) -> StorageMutationResult:
        return self._replace(
            "auth_keys",
            auth_keys,
            expected_revision=expected_revision,
        )

    def _mutate(
        self,
        collection: StorageCollection,
        mutation: StorageMutation,
    ) -> StorageMutationResult:
        upserts, delete_keys = normalize_mutation(collection, mutation)
        model, model_key = self._spec(collection)
        key_column = getattr(model, model_key)
        target_keys = {
            *(item_key(collection, item) for item in upserts),
            *delete_keys,
        }

        session = self.Session()
        try:
            self._begin_write(session)
            revision_row = self._locked_revision(session, collection)
            current_revision = self._revision_value(collection, revision_row.version)
            self._check_revision(
                collection,
                mutation.expected_revision,
                current_revision,
            )
            rows = (
                session.query(model).filter(key_column.in_(target_keys)).all()
                if target_keys
                else []
            )
            existing = {str(getattr(row, model_key)): row for row in rows}
            inserted = 0
            updated = 0
            deleted = 0

            for key in delete_keys:
                row = existing.get(key)
                if row is not None:
                    session.delete(row)
                    deleted += 1

            for item in upserts:
                key = item_key(collection, item)
                serialized = self._serialize(item)
                row = existing.get(key)
                if row is None:
                    session.add(model(**{model_key: key}, data=serialized))
                    inserted += 1
                elif self._deserialize(row.data) != item:
                    row.data = serialized
                    updated += 1

            if inserted or updated or deleted:
                revision_row.version += 1
            session.commit()
            return StorageMutationResult(
                revision=self._revision_value(collection, revision_row.version),
                inserted=inserted,
                updated=updated,
                deleted=deleted,
            )
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def mutate_accounts(self, mutation: StorageMutation) -> StorageMutationResult:
        return self._mutate("accounts", mutation)

    def mutate_auth_keys(self, mutation: StorageMutation) -> StorageMutationResult:
        return self._mutate("auth_keys", mutation)

    def _db_type(self) -> str:
        dialect = self.engine.dialect.name
        return "postgresql" if dialect == "postgres" else dialect

    def get_capabilities(self) -> StorageCapabilities:
        return StorageCapabilities(
            atomic_mutations=True,
            compare_and_swap=True,
            cross_process_safe=True,
            distributed_safe=self.engine.dialect.name != "sqlite",
            transactional=True,
        )

    def health_check(self) -> dict[str, Any]:
        try:
            session = self.Session()
            try:
                session.execute(text("SELECT 1"))
                count = session.query(AccountModel).count()
                auth_key_count = session.query(AuthKeyModel).count()
                return {
                    "status": "healthy",
                    "backend": "database",
                    "database_url": display_database_url(self.database_url),
                    "account_count": count,
                    "auth_key_count": auth_key_count,
                }
            finally:
                session.close()
        except Exception as exc:
            return {
                "status": "unhealthy",
                "backend": "database",
                "error": str(exc),
            }

    def get_backend_info(self) -> dict[str, Any]:
        db_type = self._db_type()
        return {
            "type": "database",
            "db_type": db_type,
            "description": f"应用数据库（{db_type}）",
            "database_url": display_database_url(self.database_url),
        }
