from __future__ import annotations

import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from services.proxy_service import (
    ProxyRuntimeProfile,
    ProxySettingsStore,
)


class _Config:
    def __init__(self) -> None:
        self.data = {
            "proxy_groups": [{
                "id": "image-egress",
                "enabled": True,
                "nodes": [{
                    "id": "node-a",
                    "name": "Node A",
                    "url": "http://127.0.0.1:18080",
                    "enabled": True,
                    "image_concurrency_limit": 1,
                }],
            }],
        }

    @staticmethod
    def get_proxy_runtime_settings() -> dict[str, object]:
        return {}

    @staticmethod
    def get_proxy_settings() -> str:
        return ""


class ProxyEgressCapacityTests(unittest.TestCase):
    @staticmethod
    def _profile() -> ProxyRuntimeProfile:
        return ProxyRuntimeProfile(
            proxy_url="http://127.0.0.1:18080",
            egress_key="proxy:test",
            image_concurrency_limit=1,
        )

    def test_plain_egress_waits_for_capacity_and_balances_inflight(self) -> None:
        store = ProxySettingsStore(_Config())
        profile = self._profile()
        store._egress_inflight[profile.egress_key] = 1
        waiter_blocked = threading.Event()
        waiter_acquired = threading.Event()

        class ObservableCondition(threading.Condition):
            def wait(self, timeout: float | None = None) -> bool:
                waiter_blocked.set()
                return super().wait(timeout)

        def acquire() -> None:
            store.acquire_image_egress(profile)
            waiter_acquired.set()

        store._egress_condition = ObservableCondition(store._lock)
        waiter = threading.Thread(target=acquire, daemon=True)
        waiter.start()
        try:
            self.assertTrue(waiter_blocked.wait(timeout=0.5))
            self.assertFalse(waiter_acquired.is_set())
            self.assertEqual(store._egress_inflight, {profile.egress_key: 1})

            store.release_image_egress(profile)
            self.assertTrue(waiter_acquired.wait(timeout=0.5))
            waiter.join(timeout=0.5)
            self.assertFalse(waiter.is_alive())
            self.assertEqual(store._egress_inflight, {profile.egress_key: 1})
        finally:
            if not waiter_acquired.is_set():
                store.release_image_egress(profile)
            waiter.join(timeout=0.5)

        store.release_image_egress(profile)
        self.assertEqual(store._egress_inflight, {})

    def test_non_reserving_group_lookup_does_not_change_inflight(self) -> None:
        store = ProxySettingsStore(_Config())
        key = "group:image-egress:node-a"
        store._egress_inflight[key] = 1

        selected = store.get_profile(
            proxy="group:image-egress",
            upstream=True,
            reserve_image_egress=False,
        )

        self.assertFalse(selected.image_egress_reserved)
        self.assertEqual(store._egress_inflight, {key: 1})

    def test_release_wakes_group_waiter_and_balances_inflight(self) -> None:
        store = ProxySettingsStore(_Config())
        occupied = ProxyRuntimeProfile(
            proxy_url="http://127.0.0.1:18080",
            egress_key="group:image-egress:node-a",
            image_concurrency_limit=1,
            image_egress_reserved=True,
        )
        store._egress_inflight[occupied.egress_key] = 1
        waiter_blocked = threading.Event()

        class ObservableCondition(threading.Condition):
            def wait(self, timeout: float | None = None) -> bool:
                waiter_blocked.set()
                return super().wait(timeout)

        store._egress_condition = ObservableCondition(store._lock)
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                store.get_profile,
                proxy="group:image-egress",
                upstream=True,
                reserve_image_egress=True,
            )
            self.assertTrue(waiter_blocked.wait(timeout=0.5))
            store.release_image_egress(occupied)
            selected = future.result(timeout=0.5)

        self.assertTrue(selected.image_egress_reserved)
        self.assertEqual(store._egress_inflight, {selected.egress_key: 1})
        store.release_image_egress(selected)
        self.assertEqual(store._egress_inflight, {})


if __name__ == "__main__":
    unittest.main()
