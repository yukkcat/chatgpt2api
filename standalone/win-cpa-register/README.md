# Windows CPA Registrar Exporter

This folder contains a standalone Windows tool for registration and CPA auth-file export.

It uses the existing registration core, but it does not start the web app and does not write to the project account pool.

## GUI

Use the GUI build for normal local use:

```text
dist\cpa-register-win-gui.exe
```

The window lets you configure:

- total registrations and thread count
- proxy
- export directory
- mail provider credentials
- optional CPA upload endpoint and secret key

Click "保存配置", then "开始注册". Logs appear in the "运行日志" tab.

## Output

Each successful registration creates:

- `cpa_auth_files/codex-<email>-<hash>.json`: CPA / CLIProxyAPI Codex auth file.
- `cpa_auth_files/raw_results.jsonl`: raw registration records with email, password, access token, refresh token, and id token.
- `cpa_auth_files/summary.jsonl`: task success/failure summary.

The CPA JSON shape is:

```json
{
  "type": "codex",
  "access_token": "...",
  "refresh_token": "...",
  "id_token": "...",
  "account_id": "...",
  "last_refresh": "...",
  "email": "...",
  "expired": "..."
}
```

## Build EXE

Run from PowerShell:

```powershell
cd standalone\win-cpa-register
.\build_exe.ps1
```

The executables are written to:

```text
standalone\win-cpa-register\dist\cpa-register-win.exe
standalone\win-cpa-register\dist\cpa-register-win-gui.exe
```

The first build also creates:

```text
standalone\win-cpa-register\dist\config.json
```

The GUI can edit that config directly.

## Run From Source

```powershell
python standalone\win-cpa-register\win_cpa_register.py --config standalone\win-cpa-register\config.json
```

If the config file does not exist, the tool creates one and exits.

To launch the GUI from source:

```powershell
python standalone\win-cpa-register\win_cpa_register_gui.py
```

## Config

You can copy the `mail` section from the main project's `data/register.json`.

Example:

```json
{
  "proxy": "",
  "total": 5,
  "threads": 2,
  "export_dir": "cpa_auth_files",
  "save_raw_results": true,
  "mail": {
    "request_timeout": 30,
    "wait_timeout": 30,
    "wait_interval": 2,
    "providers": [
      {
        "enable": true,
        "type": "tempmail_lol",
        "api_key": "YOUR_KEY",
        "domain": []
      }
    ]
  },
  "cpa_pools": [
    {
      "enable": false,
      "name": "local-cpa",
      "base_url": "http://127.0.0.1:8317",
      "secret_key": "YOUR_CPA_SECRET"
    }
  ]
}
```

If `cpa_pools[*].enable` is `true`, the tool uploads each generated JSON file to:

```text
POST /v0/management/auth-files?name=<file>.json
```

Use `--no-upload` to force file export only.

## Command Options

```text
--config <path>   Use a specific config file.
--total <n>       Override registration count.
--threads <n>     Override worker count.
--out <path>      Override export directory.
--no-upload       Export files only.
```
