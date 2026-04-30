from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

import win_cpa_register as core


PROVIDER_TYPES = (
    "tempmail_lol",
    "cloudflare_temp_email",
    "duckmail",
    "gptmail",
    "moemail",
    "yyds_mail",
)


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def config_path() -> Path:
    return app_dir() / "config.json"


def load_or_create_config() -> dict:
    path = config_path()
    if not path.exists():
        cfg = core._deep_copy(core.DEFAULT_CONFIG)
        core.save_config(path, cfg)
        return cfg
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, dict):
        raise ValueError("config.json must be a JSON object")
    cfg = core._merge_dict(core._deep_copy(core.DEFAULT_CONFIG), raw)
    cfg["mail"]["providers"] = list(cfg.get("mail", {}).get("providers") or [])
    cfg["cpa_pools"] = list(cfg.get("cpa_pools") or [])
    return cfg


def first_dict(items: object, fallback: dict) -> dict:
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                return dict(item)
    return dict(fallback)


def csv_to_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def list_to_csv(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    text = str(value or "").strip()
    return text


class RegisterGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("CPA 注册机")
        self.geometry("980x720")
        self.minsize(860, 620)

        self.cfg = load_or_create_config()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.running = False

        self._build_vars()
        self._build_ui()
        self._load_vars_from_config()
        self.after(150, self._drain_logs)

    def _build_vars(self) -> None:
        self.total_var = tk.StringVar()
        self.threads_var = tk.StringVar()
        self.proxy_var = tk.StringVar()
        self.export_dir_var = tk.StringVar()
        self.save_raw_var = tk.BooleanVar(value=True)

        self.mail_enable_var = tk.BooleanVar(value=True)
        self.mail_type_var = tk.StringVar(value=PROVIDER_TYPES[0])
        self.mail_api_base_var = tk.StringVar()
        self.mail_api_key_var = tk.StringVar()
        self.mail_admin_password_var = tk.StringVar()
        self.mail_domain_var = tk.StringVar()
        self.mail_default_domain_var = tk.StringVar()
        self.mail_subdomain_var = tk.StringVar()
        self.mail_expiry_var = tk.StringVar()
        self.mail_wildcard_var = tk.BooleanVar(value=False)

        self.cpa_enable_var = tk.BooleanVar(value=False)
        self.cpa_name_var = tk.StringVar()
        self.cpa_base_url_var = tk.StringVar()
        self.cpa_secret_key_var = tk.StringVar()

        self.status_var = tk.StringVar(value="准备就绪")

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="Windows 本地 CPA 注册机", font=("Microsoft YaHei UI", 16, "bold")).pack(side="left")
        ttk.Label(header, textvariable=self.status_var).pack(side="right")

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True)

        self.basic_tab = ttk.Frame(notebook, padding=12)
        self.mail_tab = ttk.Frame(notebook, padding=12)
        self.cpa_tab = ttk.Frame(notebook, padding=12)
        self.log_tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.basic_tab, text="基础配置")
        notebook.add(self.mail_tab, text="邮箱配置")
        notebook.add(self.cpa_tab, text="CPA 同步")
        notebook.add(self.log_tab, text="运行日志")

        self._build_basic_tab()
        self._build_mail_tab()
        self._build_cpa_tab()
        self._build_log_tab()

        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=(10, 0))
        self.save_button = ttk.Button(actions, text="保存配置", command=self.save_config)
        self.start_button = ttk.Button(actions, text="开始注册", command=self.start_register)
        self.open_button = ttk.Button(actions, text="打开导出目录", command=self.open_export_dir)
        self.save_button.pack(side="left")
        self.start_button.pack(side="left", padx=8)
        self.open_button.pack(side="left")

    def _row(self, parent: ttk.Frame, label: str, widget: tk.Widget, row: int, help_text: str = "") -> None:
        ttk.Label(parent, text=label, width=16).grid(row=row, column=0, sticky="w", pady=6)
        widget.grid(row=row, column=1, sticky="ew", pady=6)
        if help_text:
            ttk.Label(parent, text=help_text, foreground="#666").grid(row=row, column=2, sticky="w", padx=(10, 0))
        parent.columnconfigure(1, weight=1)

    def _build_basic_tab(self) -> None:
        self._row(self.basic_tab, "注册数量", ttk.Entry(self.basic_tab, textvariable=self.total_var), 0)
        self._row(self.basic_tab, "线程数", ttk.Entry(self.basic_tab, textvariable=self.threads_var), 1)
        self._row(self.basic_tab, "代理", ttk.Entry(self.basic_tab, textvariable=self.proxy_var), 2, "例如 http://127.0.0.1:7890")

        export_frame = ttk.Frame(self.basic_tab)
        ttk.Entry(export_frame, textvariable=self.export_dir_var).pack(side="left", fill="x", expand=True)
        ttk.Button(export_frame, text="选择", command=self.choose_export_dir).pack(side="left", padx=(8, 0))
        self._row(self.basic_tab, "导出目录", export_frame, 3)

        ttk.Checkbutton(self.basic_tab, text="保存 raw_results.jsonl（包含邮箱、密码和完整 token）", variable=self.save_raw_var).grid(
            row=4,
            column=1,
            sticky="w",
            pady=8,
        )
        ttk.Label(
            self.basic_tab,
            text=f"配置文件：{config_path()}",
            foreground="#555",
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(18, 0))

    def _build_mail_tab(self) -> None:
        ttk.Checkbutton(self.mail_tab, text="启用邮箱 Provider", variable=self.mail_enable_var).grid(row=0, column=1, sticky="w", pady=6)
        provider_box = ttk.Combobox(self.mail_tab, textvariable=self.mail_type_var, values=PROVIDER_TYPES, state="readonly")
        self._row(self.mail_tab, "类型", provider_box, 1)
        self._row(self.mail_tab, "API Base", ttk.Entry(self.mail_tab, textvariable=self.mail_api_base_var), 2, "自建邮箱服务才需要")
        self._row(self.mail_tab, "API Key", ttk.Entry(self.mail_tab, textvariable=self.mail_api_key_var, show="*"), 3)
        self._row(self.mail_tab, "Admin 密码", ttk.Entry(self.mail_tab, textvariable=self.mail_admin_password_var, show="*"), 4)
        self._row(self.mail_tab, "域名", ttk.Entry(self.mail_tab, textvariable=self.mail_domain_var), 5, "多个用英文逗号分隔")
        self._row(self.mail_tab, "默认域名", ttk.Entry(self.mail_tab, textvariable=self.mail_default_domain_var), 6)
        self._row(self.mail_tab, "子域名", ttk.Entry(self.mail_tab, textvariable=self.mail_subdomain_var), 7)
        self._row(self.mail_tab, "过期时间", ttk.Entry(self.mail_tab, textvariable=self.mail_expiry_var), 8)
        ttk.Checkbutton(self.mail_tab, text="Wildcard 模式", variable=self.mail_wildcard_var).grid(row=9, column=1, sticky="w", pady=6)

    def _build_cpa_tab(self) -> None:
        ttk.Checkbutton(self.cpa_tab, text="注册成功后同步上传到 CPA", variable=self.cpa_enable_var).grid(row=0, column=1, sticky="w", pady=6)
        self._row(self.cpa_tab, "名称", ttk.Entry(self.cpa_tab, textvariable=self.cpa_name_var), 1)
        self._row(self.cpa_tab, "CPA 地址", ttk.Entry(self.cpa_tab, textvariable=self.cpa_base_url_var), 2, "例如 http://127.0.0.1:8317")
        self._row(self.cpa_tab, "Secret Key", ttk.Entry(self.cpa_tab, textvariable=self.cpa_secret_key_var, show="*"), 3)
        ttk.Label(
            self.cpa_tab,
            text="不启用 CPA 同步时，也会在导出目录生成 codex-*.json，可以手动导入 CPA。",
            foreground="#555",
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(18, 0))

    def _build_log_tab(self) -> None:
        self.log_text = scrolledtext.ScrolledText(self.log_tab, height=20, wrap="word")
        self.log_text.pack(fill="both", expand=True)
        self.log_text.configure(state="disabled")

    def _load_vars_from_config(self) -> None:
        cfg = self.cfg
        provider = first_dict(cfg.get("mail", {}).get("providers"), core.DEFAULT_CONFIG["mail"]["providers"][0])
        pool = first_dict(cfg.get("cpa_pools"), core.DEFAULT_CONFIG["cpa_pools"][0])

        self.total_var.set(str(cfg.get("total") or 1))
        self.threads_var.set(str(cfg.get("threads") or 1))
        self.proxy_var.set(str(cfg.get("proxy") or ""))
        self.export_dir_var.set(str(cfg.get("export_dir") or "cpa_auth_files"))
        self.save_raw_var.set(bool(cfg.get("save_raw_results", True)))

        self.mail_enable_var.set(bool(provider.get("enable")))
        self.mail_type_var.set(str(provider.get("type") or PROVIDER_TYPES[0]))
        self.mail_api_base_var.set(str(provider.get("api_base") or ""))
        self.mail_api_key_var.set(str(provider.get("api_key") or ""))
        self.mail_admin_password_var.set(str(provider.get("admin_password") or ""))
        self.mail_domain_var.set(list_to_csv(provider.get("domain")))
        self.mail_default_domain_var.set(str(provider.get("default_domain") or ""))
        self.mail_subdomain_var.set(str(provider.get("subdomain") or ""))
        self.mail_expiry_var.set(str(provider.get("expiry_time") or ""))
        self.mail_wildcard_var.set(bool(provider.get("wildcard")))

        self.cpa_enable_var.set(bool(pool.get("enable")))
        self.cpa_name_var.set(str(pool.get("name") or "local-cpa"))
        self.cpa_base_url_var.set(str(pool.get("base_url") or "http://127.0.0.1:8317"))
        self.cpa_secret_key_var.set(str(pool.get("secret_key") or ""))

    def _config_from_vars(self) -> dict:
        provider = {
            "enable": bool(self.mail_enable_var.get()),
            "type": self.mail_type_var.get().strip(),
            "api_base": self.mail_api_base_var.get().strip(),
            "api_key": self.mail_api_key_var.get().strip(),
            "admin_password": self.mail_admin_password_var.get().strip(),
            "domain": csv_to_list(self.mail_domain_var.get()),
            "default_domain": self.mail_default_domain_var.get().strip(),
            "subdomain": self.mail_subdomain_var.get().strip(),
            "wildcard": bool(self.mail_wildcard_var.get()),
        }
        expiry = self.mail_expiry_var.get().strip()
        if expiry:
            try:
                provider["expiry_time"] = int(expiry)
            except ValueError:
                provider["expiry_time"] = 0

        pool = {
            "enable": bool(self.cpa_enable_var.get()),
            "name": self.cpa_name_var.get().strip() or "local-cpa",
            "base_url": self.cpa_base_url_var.get().strip(),
            "secret_key": self.cpa_secret_key_var.get().strip(),
        }

        return {
            "proxy": self.proxy_var.get().strip(),
            "total": max(1, int(self.total_var.get() or 1)),
            "threads": max(1, int(self.threads_var.get() or 1)),
            "export_dir": self.export_dir_var.get().strip() or "cpa_auth_files",
            "save_raw_results": bool(self.save_raw_var.get()),
            "mail": {
                "request_timeout": int(self.cfg.get("mail", {}).get("request_timeout") or 30),
                "wait_timeout": int(self.cfg.get("mail", {}).get("wait_timeout") or 30),
                "wait_interval": int(self.cfg.get("mail", {}).get("wait_interval") or 2),
                "providers": [provider],
            },
            "cpa_pools": [pool],
        }

    def save_config(self) -> bool:
        try:
            cfg = self._config_from_vars()
        except Exception as exc:
            messagebox.showerror("配置错误", str(exc))
            return False
        core.save_config(config_path(), cfg)
        self.cfg = cfg
        self.status_var.set("配置已保存")
        self._append_log(f"配置已保存：{config_path()}")
        return True

    def choose_export_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择导出目录")
        if selected:
            self.export_dir_var.set(selected)

    def open_export_dir(self) -> None:
        cfg = self._config_from_vars()
        output_dir = core.resolve_output_dir(cfg, config_path())
        output_dir.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(output_dir)])

    def start_register(self) -> None:
        if self.running:
            messagebox.showinfo("正在运行", "注册任务正在运行中。")
            return
        if not self.save_config():
            return
        if not self.mail_enable_var.get():
            messagebox.showerror("配置错误", "请先启用并配置邮箱 Provider。")
            return
        if self.cpa_enable_var.get() and (not self.cpa_base_url_var.get().strip() or not self.cpa_secret_key_var.get().strip()):
            messagebox.showerror("配置错误", "启用 CPA 同步时必须填写 CPA 地址和 Secret Key。")
            return

        self.running = True
        self.start_button.configure(state="disabled")
        self.status_var.set("运行中")
        self.worker = threading.Thread(target=self._run_register_job, args=(self.cfg,), daemon=True)
        self.worker.start()

    def _run_register_job(self, cfg: dict) -> None:
        core.set_log_sink(lambda text: self.log_queue.put(text))
        try:
            core._ensure_repo_imports()
            from services.register import openai_register

            output_dir = core.resolve_output_dir(cfg, config_path())
            raw_path = output_dir / "raw_results.jsonl"
            upload_pools = core._enabled_cpa_pools(cfg, no_upload=False)

            openai_register.config.update(
                {
                    "mail": cfg["mail"],
                    "proxy": cfg["proxy"],
                    "total": cfg["total"],
                    "threads": cfg["threads"],
                }
            )
            openai_register.register_log_sink = lambda text, color="": core.log(text)
            with openai_register.stats_lock:
                openai_register.stats.update({"done": 0, "success": 0, "fail": 0, "start_time": time.time()})

            total = int(cfg["total"])
            threads = min(max(1, int(cfg["threads"])), total)
            success = 0
            failed = 0
            core.log(f"配置文件: {config_path()}")
            core.log(f"导出目录: {output_dir}")
            core.log(f"开始注册: total={total}, threads={threads}, cpa_upload_pools={len(upload_pools)}")

            with ThreadPoolExecutor(max_workers=threads) as executor:
                futures = {
                    executor.submit(core.run_one, index, cfg, output_dir, raw_path, upload_pools): index
                    for index in range(1, total + 1)
                }
                for future in as_completed(futures):
                    item = future.result()
                    success += 1 if item.get("ok") else 0
                    failed += 0 if item.get("ok") else 1
                    with core.write_lock:
                        core._append_jsonl(output_dir / "summary.jsonl", item)

            core.log(f"完成: success={success}, failed={failed}")
        except Exception as exc:
            core.log(f"运行失败: {exc}")
        finally:
            try:
                from services.register import openai_register

                openai_register.register_log_sink = None
            except Exception:
                pass
            core.set_log_sink(None)
            self.log_queue.put("__DONE__")

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _drain_logs(self) -> None:
        while True:
            try:
                item = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if item == "__DONE__":
                self.running = False
                self.start_button.configure(state="normal")
                self.status_var.set("已结束")
            else:
                self._append_log(item)
        self.after(150, self._drain_logs)


def main() -> int:
    if "--smoke" in sys.argv:
        cfg = load_or_create_config()
        print(json.dumps({"ok": True, "config": str(config_path()), "total": cfg.get("total")}, ensure_ascii=False))
        return 0
    app = RegisterGui()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
