from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


DEFAULT_CONFIG = {
    "proxy": "",
    "total": 1,
    "threads": 1,
    "export_dir": "cpa_auth_files",
    "save_raw_results": True,
    "mail": {
        "request_timeout": 30,
        "wait_timeout": 30,
        "wait_interval": 2,
        "providers": [
            {
                "enable": False,
                "type": "tempmail_lol",
                "api_key": "",
                "domain": [],
            }
        ],
    },
    "cpa_pools": [
        {
            "enable": False,
            "name": "local-cpa",
            "base_url": "http://127.0.0.1:8317",
            "secret_key": "",
        }
    ],
}


print_lock = threading.Lock()
write_lock = threading.Lock()
log_sink = None


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _ensure_repo_imports() -> None:
    root = _repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def log(message: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    text = f"{stamp} {message}"
    if log_sink:
        try:
            log_sink(text)
        except Exception:
            pass
    with print_lock:
        print(text, flush=True)


def set_log_sink(sink) -> None:
    global log_sink
    log_sink = sink


def save_config(path: Path, cfg: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _deep_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _merge_dict(base: dict, updates: dict) -> dict:
    result = dict(base)
    for key, value in updates.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict):
            result[key] = _merge_dict(result[key], value)
        else:
            result[key] = value
    return result


def _load_config(path: Path) -> dict:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        save_config(path, DEFAULT_CONFIG)
        raise SystemExit(f"Created config file: {path}\nEdit mail.providers first, then run again.")
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise SystemExit("Config file must be a JSON object.")
    cfg = _merge_dict(_deep_copy(DEFAULT_CONFIG), raw)
    cfg["total"] = max(1, int(cfg.get("total") or 1))
    cfg["threads"] = max(1, int(cfg.get("threads") or 1))
    cfg["proxy"] = str(cfg.get("proxy") or "").strip()
    cfg["export_dir"] = str(cfg.get("export_dir") or "cpa_auth_files").strip() or "cpa_auth_files"
    cfg["mail"]["providers"] = list(cfg.get("mail", {}).get("providers") or [])
    return cfg


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _decode_jwt_payload(token: object) -> dict:
    parts = _clean_text(token).split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8"))
        data = json.loads(decoded.decode("utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _expiration_from_payload(payload: dict) -> str:
    try:
        exp = int(payload.get("exp") or 0)
    except (TypeError, ValueError):
        return ""
    if exp <= 0:
        return ""
    return datetime.fromtimestamp(exp, timezone.utc).isoformat()


def _first_text(*values: object) -> str:
    for value in values:
        cleaned = _clean_text(value)
        if cleaned:
            return cleaned
    return ""


def _openai_auth_info(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    auth_info = payload.get("https://api.openai.com/auth")
    return auth_info if isinstance(auth_info, dict) else {}


def _payload_value(keys: tuple[str, ...], *payloads: dict) -> str:
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        auth_info = _openai_auth_info(payload)
        for key in keys:
            value = _clean_text(auth_info.get(key))
            if value:
                return value
            value = _clean_text(payload.get(key))
            if value:
                return value
    return ""


def build_cpa_auth_payload(record: dict) -> dict:
    access_token = _clean_text(record.get("access_token"))
    if not access_token:
        raise ValueError("access_token is required")
    id_token = _clean_text(record.get("id_token"))
    if not id_token:
        raise ValueError("id_token is required for CPA Codex auth")

    access_payload = _decode_jwt_payload(access_token)
    id_payload = _decode_jwt_payload(id_token)
    expired = _first_text(
        record.get("expired"),
        _expiration_from_payload(access_payload),
        _expiration_from_payload(id_payload),
    )
    chatgpt_user_id = _first_text(
        record.get("chatgpt_user_id"),
        _payload_value(("chatgpt_user_id", "user_id"), id_payload, access_payload),
        record.get("user_id"),
    )
    auth_subject_id = _payload_value(("sub",), id_payload, access_payload)
    record_account_id = _clean_text(record.get("account_id"))
    if record_account_id.startswith("auth0|"):
        record_account_id = ""
    chatgpt_account_id = _first_text(
        record.get("chatgpt_account_id"),
        _payload_value(("chatgpt_account_id", "account_id"), id_payload, access_payload),
        record_account_id,
        chatgpt_user_id,
    )
    account_id = _first_text(chatgpt_account_id, record.get("account_id"), auth_subject_id)
    plan_type = _payload_value(("chatgpt_plan_type",), id_payload, access_payload)

    payload = {
        "type": "codex",
        "access_token": access_token,
        "refresh_token": _clean_text(record.get("refresh_token")),
        "id_token": id_token,
        "account_id": account_id,
        "last_refresh": _first_text(record.get("last_refresh"), record.get("created_at"), datetime.now(timezone.utc).isoformat()),
        "email": _first_text(record.get("email"), id_payload.get("email"), access_payload.get("email")),
    }
    if chatgpt_account_id:
        payload["chatgpt_account_id"] = chatgpt_account_id
    if chatgpt_user_id:
        payload["chatgpt_user_id"] = chatgpt_user_id
        payload["user_id"] = chatgpt_user_id
    if plan_type:
        payload["plan_type"] = plan_type
    if expired:
        payload["expired"] = expired
    return payload


def cpa_auth_filename(record: dict) -> str:
    payload = build_cpa_auth_payload(record)
    digest = hashlib.sha1(payload["access_token"].encode("utf-8")).hexdigest()[:8]
    email = re.sub(r"[^A-Za-z0-9@._-]+", "-", payload.get("email") or "").strip(".-_")
    if email:
        return f"codex-{email[:120]}-{digest}.json"
    return f"codex-{digest}.json"


def export_cpa_file(record: dict, output_dir: Path) -> Path:
    payload = build_cpa_auth_payload(record)
    file_path = output_dir / cpa_auth_filename(record)
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(file_path)
    return file_path


def upload_cpa_file(pool: dict, file_path: Path) -> tuple[bool, str]:
    base_url = _clean_text(pool.get("base_url"))
    secret_key = _clean_text(pool.get("secret_key"))
    if not base_url or not secret_key:
        return False, "missing base_url or secret_key"
    url = f"{base_url.rstrip('/')}/v0/management/auth-files"
    try:
        response = requests.post(
            url,
            params={"name": file_path.name},
            headers={
                "Authorization": f"Bearer {secret_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            data=file_path.read_bytes(),
            timeout=30,
        )
    except Exception as exc:
        return False, str(exc)
    if 200 <= response.status_code < 300:
        return True, ""
    return False, f"HTTP {response.status_code}: {response.text[:300]}"


def _enabled_cpa_pools(cfg: dict, no_upload: bool) -> list[dict]:
    if no_upload:
        return []
    pools = cfg.get("cpa_pools") or []
    return [pool for pool in pools if isinstance(pool, dict) and bool(pool.get("enable"))]


def _append_jsonl(path: Path, item: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def resolve_output_dir(cfg: dict, config_path: Path) -> Path:
    output_dir = Path(_clean_text(cfg.get("export_dir")) or "cpa_auth_files")
    if not output_dir.is_absolute():
        output_dir = config_path.parent / output_dir
    return output_dir


def run_one(index: int, cfg: dict, output_dir: Path, raw_path: Path, upload_pools: list[dict]) -> dict:
    from services.register import openai_register

    registrar = openai_register.PlatformRegistrar(cfg["proxy"])
    try:
        started = time.time()
        result = registrar.register(index)
        file_path = export_cpa_file(result, output_dir)
        upload_results = []
        for pool in upload_pools:
            ok, error = upload_cpa_file(pool, file_path)
            upload_results.append(
                {
                    "name": _clean_text(pool.get("name")),
                    "base_url": _clean_text(pool.get("base_url")),
                    "ok": ok,
                    "error": error,
                }
            )

        with write_lock:
            if bool(cfg.get("save_raw_results", True)):
                _append_jsonl(raw_path, result)

        elapsed = time.time() - started
        log(f"[task {index}] ok {result.get('email') or ''} -> {file_path.name} ({elapsed:.1f}s)")
        for item in upload_results:
            status = "ok" if item["ok"] else f"failed: {item['error']}"
            log(f"[task {index}] upload {item['name'] or item['base_url']} {status}")
        return {"ok": True, "index": index, "email": result.get("email"), "file": str(file_path), "uploads": upload_results}
    except Exception as exc:
        log(f"[task {index}] failed: {exc}")
        return {"ok": False, "index": index, "error": str(exc)}
    finally:
        registrar.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone Windows CPA registrar exporter.")
    parser.add_argument("--config", default="", help="Path to config.json. Default: next to this exe/script.")
    parser.add_argument("--total", type=int, default=0, help="Override total registrations.")
    parser.add_argument("--threads", type=int, default=0, help="Override worker threads.")
    parser.add_argument("--out", default="", help="Override CPA export directory.")
    parser.add_argument("--no-upload", action="store_true", help="Only export files, skip CPA upload pools.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).resolve() if args.config else _app_dir() / "config.json"
    cfg = _load_config(config_path)
    if args.total > 0:
        cfg["total"] = args.total
    if args.threads > 0:
        cfg["threads"] = args.threads
    if args.out:
        cfg["export_dir"] = args.out

    if not any(bool(item.get("enable")) for item in cfg["mail"]["providers"] if isinstance(item, dict)):
        log(f"No enabled mail provider in {config_path}")
        log("Set mail.providers[*].enable = true and fill provider credentials.")
        return 2

    _ensure_repo_imports()
    from services.register import openai_register

    output_dir = Path(cfg["export_dir"])
    if not output_dir.is_absolute():
        output_dir = config_path.parent / output_dir
    raw_path = output_dir / "raw_results.jsonl"
    upload_pools = _enabled_cpa_pools(cfg, args.no_upload)

    openai_register.config.update(
        {
            "mail": cfg["mail"],
            "proxy": cfg["proxy"],
            "total": cfg["total"],
            "threads": cfg["threads"],
        }
    )
    openai_register.register_log_sink = None
    with openai_register.stats_lock:
        openai_register.stats.update({"done": 0, "success": 0, "fail": 0, "start_time": time.time()})

    log(f"Config: {config_path}")
    log(f"Export dir: {output_dir}")
    log(f"Start: total={cfg['total']}, threads={cfg['threads']}, cpa_upload_pools={len(upload_pools)}")

    total = int(cfg["total"])
    threads = min(max(1, int(cfg["threads"])), total)
    success = 0
    fail = 0
    with ThreadPoolExecutor(max_workers=threads) as executor:
        futures = {executor.submit(run_one, index, cfg, output_dir, raw_path, upload_pools): index for index in range(1, total + 1)}
        for future in as_completed(futures):
            item = future.result()
            success += 1 if item.get("ok") else 0
            fail += 0 if item.get("ok") else 1
            with write_lock:
                _append_jsonl(output_dir / "summary.jsonl", item)

    log(f"Done: success={success}, failed={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
