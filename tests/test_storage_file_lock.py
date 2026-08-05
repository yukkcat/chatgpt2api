from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from services.storage.file_lock import interprocess_lock


class StorageFileLockTests(unittest.TestCase):
    def test_unlock_failure_does_not_leak_the_process_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            lock_path = Path(temp_dir) / "storage.lock"

            with patch(
                "services.storage.file_lock._unlock",
                side_effect=OSError("unlock failed"),
            ):
                with self.assertRaisesRegex(OSError, "unlock failed"):
                    with interprocess_lock(lock_path, timeout_seconds=0.1):
                        pass

            with interprocess_lock(lock_path, timeout_seconds=0.1):
                pass


if __name__ == "__main__":
    unittest.main()
