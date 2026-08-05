from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, Literal, Sequence


StorageCollection = Literal["accounts", "auth_keys"]


class StorageRevisionConflictError(RuntimeError):
    """Raised when a compare-and-swap mutation uses a stale revision."""

    def __init__(self, collection: StorageCollection, expected: str, actual: str):
        self.collection = collection
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"stale {collection} storage revision: expected {expected!r}, actual {actual!r}"
        )


@dataclass(frozen=True, slots=True)
class StorageCapabilities:
    """Concurrency guarantees exposed by a storage adapter.

    ``cross_process_safe`` applies to processes sharing the same storage and lock
    location. ``distributed_safe`` additionally covers independent hosts.
    Snapshot replacement remains available for legacy callers, but only mutation
    calls carrying ``expected_revision`` provide compare-and-swap protection.
    """

    atomic_mutations: bool
    compare_and_swap: bool
    cross_process_safe: bool
    distributed_safe: bool
    transactional: bool

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StorageSnapshot:
    """A keyed collection snapshot; item order is not part of the contract."""

    items: list[dict[str, Any]]
    revision: str


@dataclass(frozen=True, slots=True)
class StorageMutation:
    """A batch applied atomically to one logical collection.

    Item identity is owned by the adapter contract: ``access_token`` for accounts
    and ``id`` for auth keys. A key cannot be both deleted and upserted in one
    mutation. Revisions are opaque and must only be compared for equality.
    """

    upserts: Sequence[dict[str, Any]] = ()
    delete_keys: Sequence[str] = ()
    expected_revision: str | None = None


@dataclass(frozen=True, slots=True)
class StorageMutationResult:
    revision: str
    inserted: int = 0
    updated: int = 0
    deleted: int = 0

    @property
    def changed(self) -> bool:
        return bool(self.inserted or self.updated or self.deleted)


class StorageBackend(ABC):
    """Storage seam for account and auth-key collections."""

    @abstractmethod
    def load_accounts_snapshot(self) -> StorageSnapshot:
        """Load accounts together with an opaque collection revision."""

    def load_accounts(self) -> list[dict[str, Any]]:
        """Compatibility view for callers that do not use revisions yet."""
        return self.load_accounts_snapshot().items

    @abstractmethod
    def replace_accounts(
        self,
        accounts: Sequence[dict[str, Any]],
        *,
        expected_revision: str | None = None,
    ) -> StorageMutationResult:
        """Replace the account snapshot, optionally using compare-and-swap."""

    def save_accounts(self, accounts: list[dict[str, Any]]) -> None:
        """Compatibility write; it is intentionally unconditional."""
        self.replace_accounts(accounts)

    @abstractmethod
    def mutate_accounts(self, mutation: StorageMutation) -> StorageMutationResult:
        """Atomically upsert and delete accounts."""

    def upsert_account(
        self,
        account: dict[str, Any],
        *,
        expected_revision: str | None = None,
    ) -> StorageMutationResult:
        return self.mutate_accounts(
            StorageMutation(upserts=(account,), expected_revision=expected_revision)
        )

    def delete_account(
        self,
        access_token: str,
        *,
        expected_revision: str | None = None,
    ) -> StorageMutationResult:
        return self.mutate_accounts(
            StorageMutation(delete_keys=(access_token,), expected_revision=expected_revision)
        )

    @abstractmethod
    def load_auth_keys_snapshot(self) -> StorageSnapshot:
        """Load auth keys together with an opaque collection revision."""

    def load_auth_keys(self) -> list[dict[str, Any]]:
        """Compatibility view for callers that do not use revisions yet."""
        return self.load_auth_keys_snapshot().items

    @abstractmethod
    def replace_auth_keys(
        self,
        auth_keys: Sequence[dict[str, Any]],
        *,
        expected_revision: str | None = None,
    ) -> StorageMutationResult:
        """Replace the auth-key snapshot, optionally using compare-and-swap."""

    def save_auth_keys(self, auth_keys: list[dict[str, Any]]) -> None:
        """Compatibility write; it is intentionally unconditional."""
        self.replace_auth_keys(auth_keys)

    @abstractmethod
    def mutate_auth_keys(self, mutation: StorageMutation) -> StorageMutationResult:
        """Atomically upsert and delete auth keys."""

    def upsert_auth_key(
        self,
        auth_key: dict[str, Any],
        *,
        expected_revision: str | None = None,
    ) -> StorageMutationResult:
        return self.mutate_auth_keys(
            StorageMutation(upserts=(auth_key,), expected_revision=expected_revision)
        )

    def delete_auth_key(
        self,
        key_id: str,
        *,
        expected_revision: str | None = None,
    ) -> StorageMutationResult:
        return self.mutate_auth_keys(
            StorageMutation(delete_keys=(key_id,), expected_revision=expected_revision)
        )

    @abstractmethod
    def get_capabilities(self) -> StorageCapabilities:
        """Return the concurrency guarantees implemented by this adapter."""

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Return current storage health."""

    @abstractmethod
    def get_backend_info(self) -> dict[str, Any]:
        """Return non-secret backend configuration and capabilities."""
