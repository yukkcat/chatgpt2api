"""CLIProxyAPI integration for browsing and importing remote account files."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from curl_cffi.requests import Session

from services.account_import_credentials import (
    collect_import_diagnostic_values,
    extract_import_credentials,
)
from services.account_import_job import (
    RemoteAccountImportJob,
    import_job_is_active,
    normalize_import_error as _normalize_import_error,
    normalize_import_job as _normalize_import_job,
)
from services.account_processing import (
    account_processing_slot,
    account_processing_worker_count,
)
from services.proxy_service import proxy_settings
from services.storage.remote_import_configuration_repository import (
    RemoteImportConfigurationRepository,
)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _import_error_context(pool: dict, *sources: object) -> dict[str, tuple[str, ...]]:
    sensitive_values, proxy_values = collect_import_diagnostic_values(
        {"secret_key": pool.get("secret_key")},
        *sources,
    )
    return {
        "sensitive_values": sensitive_values,
        "proxy_values": proxy_values,
    }

def _normalize_pool(raw: dict, *, fail_unfinished: bool = True) -> dict:
    secret_key = str(raw.get("secret_key") or "").strip()
    return {
        "id": str(raw.get("id") or _new_id()).strip(),
        "name": str(raw.get("name") or "").strip(),
        "base_url": str(raw.get("base_url") or "").strip(),
        "secret_key": secret_key,
        "import_job": _normalize_import_job(
            raw.get("import_job"),
            fail_unfinished=fail_unfinished,
            **_import_error_context({"secret_key": secret_key}),
        ),
    }


def _management_headers(secret_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {secret_key}",
        "Accept": "application/json",
    }


class CPAConfig:
    def __init__(
        self,
        repository: RemoteImportConfigurationRepository | None = None,
        *,
        database_url: str | None = None,
    ) -> None:
        if repository is not None and database_url is not None:
            raise ValueError("provide repository or database_url, not both")
        self.repository = repository or RemoteImportConfigurationRepository(database_url)
        self.repository.update(
            "cpa",
            lambda items: self._normalize_items(items, fail_unfinished=True),
        )

    @staticmethod
    def _normalize_items(items: list[dict], *, fail_unfinished: bool) -> list[dict]:
        return [
            _normalize_pool(item, fail_unfinished=fail_unfinished)
            for item in items
            if isinstance(item, dict)
        ]

    def _load(self) -> list[dict]:
        return self._normalize_items(
            self.repository.load("cpa"),
            fail_unfinished=False,
        )

    def list_pools(self) -> list[dict]:
        return [dict(pool) for pool in self._load()]

    def get_pool(self, pool_id: str) -> dict | None:
        for pool in self._load():
            if pool["id"] == pool_id:
                return dict(pool)
        return None

    def add_pool(self, name: str, base_url: str, secret_key: str) -> dict:
        pool = _normalize_pool({"id": _new_id(), "name": name, "base_url": base_url, "secret_key": secret_key}, fail_unfinished=False)
        self.repository.update("cpa", lambda items: [*items, pool])
        return dict(pool)

    def update_pool(self, pool_id: str, updates: dict) -> dict | None:
        result: dict | None = None

        def update(items: list[dict]) -> list[dict]:
            nonlocal result
            pools = self._normalize_items(items, fail_unfinished=False)
            for index, pool in enumerate(pools):
                if pool["id"] != pool_id:
                    continue
                if import_job_is_active(pool.get("import_job")):
                    raise ValueError("CPA import job is active")
                merged = {**pool, **{key: value for key, value in updates.items() if value is not None}, "id": pool_id}
                pools[index] = _normalize_pool(merged, fail_unfinished=False)
                result = dict(pools[index])
                break
            return pools

        self.repository.update("cpa", update)
        return result

    def delete_pool(self, pool_id: str) -> bool:
        removed = False

        def delete(items: list[dict]) -> list[dict]:
            nonlocal removed
            pools = self._normalize_items(items, fail_unfinished=False)
            for pool in pools:
                if pool["id"] == pool_id and import_job_is_active(pool.get("import_job")):
                    raise ValueError("CPA import job is active")
            remaining = [pool for pool in pools if pool["id"] != pool_id]
            removed = len(remaining) < len(pools)
            return remaining

        self.repository.update("cpa", delete)
        return removed

    def set_import_job(self, pool_id: str, import_job: dict | None, *, expected_job_id: str | None = None) -> dict | None:
        result: dict | None = None

        def update(items: list[dict]) -> list[dict]:
            nonlocal result
            pools = self._normalize_items(items, fail_unfinished=False)
            for index, pool in enumerate(pools):
                if pool["id"] != pool_id:
                    continue
                current_job = pool.get("import_job")
                current_job_id = str((current_job or {}).get("job_id") or "").strip()
                if expected_job_id is not None and current_job_id != str(expected_job_id).strip():
                    return pools
                next_pool = dict(pool)
                next_pool["import_job"] = _normalize_import_job(
                    import_job,
                    fail_unfinished=False,
                    **_import_error_context(pool),
                )
                pools[index] = next_pool
                result = dict(next_pool)
                break
            return pools

        self.repository.update("cpa", update)
        return result

    def start_import_job(self, pool_id: str, import_job: dict) -> dict | None:
        result: dict | None = None

        def update(items: list[dict]) -> list[dict]:
            nonlocal result
            pools = self._normalize_items(items, fail_unfinished=False)
            for index, pool in enumerate(pools):
                if pool["id"] != pool_id:
                    continue
                current = pool.get("import_job")
                if import_job_is_active(current):
                    raise ValueError("an import job is already running for this CPA pool")
                next_pool = dict(pool)
                next_pool["import_job"] = _normalize_import_job(
                    import_job,
                    fail_unfinished=False,
                    **_import_error_context(pool),
                )
                pools[index] = next_pool
                result = dict(next_pool)
                break
            return pools

        self.repository.update("cpa", update)
        return result

    def get_import_job(self, pool_id: str) -> dict | None:
        for pool in self._load():
            if pool["id"] == pool_id:
                job = pool.get("import_job")
                return dict(job) if isinstance(job, dict) else None
        return None


def list_remote_files(pool: dict) -> list[dict]:
    base_url = str(pool.get("base_url") or "").strip()
    secret_key = str(pool.get("secret_key") or "").strip()
    if not base_url or not secret_key:
        return []

    url = f"{base_url.rstrip('/')}/v0/management/auth-files"
    error_context = _import_error_context(pool)
    session = None
    try:
        session_kwargs = proxy_settings.build_session_kwargs(verify=True)
        error_context = _import_error_context(
            pool,
            {"proxy": session_kwargs.get("proxy")},
        )
        session = Session(**session_kwargs)
        response = session.get(url, headers=_management_headers(secret_key), timeout=30)
        if not response.ok:
            raise RuntimeError(f"remote list failed: HTTP {response.status_code}")
        payload = response.json()
    except Exception as exc:
        error = _normalize_import_error(
            exc,
            default_name="CPA server",
            **error_context,
        )["error"]
        raise RuntimeError(error) from None
    finally:
        if session is not None:
            session.close()

    files = payload.get("files") if isinstance(payload, dict) else None
    if not isinstance(files, list):
        raise RuntimeError("remote list payload is invalid")

    items: list[dict] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        email = str(item.get("email") or item.get("account") or "").strip()
        if not name:
            continue
        items.append({"name": name, "email": email})
    return items


def fetch_remote_account_payload(pool: dict, file_name: str) -> tuple[dict | None, str | None]:
    base_url = str(pool.get("base_url") or "").strip()
    secret_key = str(pool.get("secret_key") or "").strip()
    file_name = str(file_name or "").strip()
    if not base_url or not secret_key or not file_name:
        return None, "invalid request"

    url = f"{base_url.rstrip('/')}/v0/management/auth-files/download"
    error_context = _import_error_context(pool)
    session = None
    try:
        session_kwargs = proxy_settings.build_session_kwargs(verify=True)
        error_context = _import_error_context(
            pool,
            {"proxy": session_kwargs.get("proxy")},
        )
        session = Session(**session_kwargs)
        response = session.get(url, headers=_management_headers(secret_key), params={"name": file_name}, timeout=30)
        if not response.ok:
            return None, f"HTTP {response.status_code}"
        payload = response.json()
    except Exception as exc:
        return None, _normalize_import_error(
            exc,
            default_name=file_name,
            **error_context,
        )["error"]
    finally:
        if session is not None:
            session.close()

    if not isinstance(payload, dict):
        return None, "invalid payload"

    account_payload = extract_import_credentials(payload)
    if not account_payload.get("access_token"):
        return None, "missing access_token"
    account_payload["source_type"] = "codex"
    return account_payload, None


class CPAImportService:
    def __init__(self, cpa_config: CPAConfig):
        self._config = cpa_config

    def _job(
        self,
        pool_id: str,
        pool: dict,
        total: int,
        *,
        job_id: str = "",
    ) -> RemoteAccountImportJob:
        return RemoteAccountImportJob(
            self._config,
            source_id=pool_id,
            total=total,
            worker_label="CPA import worker",
            error_context=lambda *sources: _import_error_context(pool, *sources),
            job_id=job_id,
        )

    def start_import(self, pool: dict, selected_files: list[str]) -> dict:
        names = list(dict.fromkeys(str(name or "").strip() for name in selected_files if str(name or "").strip()))
        if not names:
            raise ValueError("selected files is required")

        pool_id = str(pool.get("id") or "").strip()
        import_job = self._job(pool_id, pool, len(names))
        saved_job = import_job.reserve()
        if saved_job is None:
            raise ValueError("pool not found")
        import_job.start_worker(
            target=self._run_import_guarded,
            args=(pool_id, pool, names, import_job.job_id),
            name=f"cpa-import-{pool_id}",
        )
        return saved_job

    def _run_import_guarded(
        self,
        pool_id: str,
        pool: dict,
        names: list[str],
        job_id: str,
    ) -> None:
        self._job(
            pool_id,
            pool,
            len(names),
            job_id=job_id,
        ).run_guarded(
            self._run_import,
            pool_id,
            pool,
            names,
            job_id=job_id,
        )

    def _run_import(self, pool_id: str, pool: dict, names: list[str], job_id: str = "") -> None:
        import_job = self._job(
            pool_id,
            pool,
            len(names),
            job_id=job_id,
        )
        if not import_job.begin():
            return

        fetched_accounts: list[tuple[str, dict]] = []
        max_workers = max(1, account_processing_worker_count(len(names)))

        def fetch(file_name: str) -> tuple[dict | None, str | None]:
            with account_processing_slot():
                return fetch_remote_account_payload(pool, file_name)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(fetch, name): name for name in names}
            for future in as_completed(future_map):
                file_name = future_map[future]
                try:
                    payload, error = future.result()
                except Exception as exc:
                    payload, error = None, str(exc)

                if payload:
                    fetched_accounts.append((file_name, payload))
                    if not import_job.record_fetch(file_name):
                        return
                else:
                    if not import_job.record_fetch(
                        file_name,
                        error=error or "unknown error",
                    ):
                        return
        import_job.finish(fetched_accounts)


cpa_config = CPAConfig()
cpa_import_service = CPAImportService(cpa_config)
