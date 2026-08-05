from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import init_proxy_config


class InitProxyConfigTests(unittest.TestCase):
    def run_init(
        self,
        initial: dict[str, object],
        *,
        default_proxy: str | None = "http://privoxy:8118",
        **environment: str,
    ) -> dict[str, object]:
        with TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_text(json.dumps(initial), encoding="utf-8")
            values = {
                "CHATGPT2API_CONFIG_FILE": str(config_path),
                **environment,
            }
            if default_proxy is not None:
                values["CHATGPT2API_DEFAULT_PROXY"] = default_proxy
            with patch.dict(os.environ, values, clear=True):
                self.assertEqual(init_proxy_config.main(), 0)
            return json.loads(config_path.read_text(encoding="utf-8"))

    def test_warp_initialization_writes_top_level_default_proxy(self) -> None:
        runtime = init_proxy_config._warp_runtime_defaults()

        result = self.run_init({"proxy_runtime": runtime})

        self.assertEqual(result["proxy"], "http://privoxy:8118")
        self.assertNotIn("egress_mode", result["proxy_runtime"])
        self.assertNotIn("proxy_url", result["proxy_runtime"])

    def test_legacy_runtime_proxy_is_migrated_to_top_level_proxy(self) -> None:
        legacy_runtime = init_proxy_config._warp_runtime_defaults()
        legacy_runtime.update({
            "egress_mode": "single_proxy",
            "proxy_url": "http://legacy.example:8080",
        })

        result = self.run_init(
            {"proxy_runtime": legacy_runtime},
            default_proxy=None,
        )

        self.assertEqual(result["proxy"], "http://legacy.example:8080")
        self.assertNotIn("egress_mode", result["proxy_runtime"])
        self.assertNotIn("proxy_url", result["proxy_runtime"])

    def test_explicit_direct_default_is_preserved(self) -> None:
        result = self.run_init({"proxy": "direct"})

        self.assertEqual(result["proxy"], "direct")


if __name__ == "__main__":
    unittest.main()
