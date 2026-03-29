from __future__ import annotations

import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rompatcher.updater import (
    ReleaseAsset,
    ReleaseInfo,
    build_windows_update_script,
    download_release_asset,
    find_available_update,
    install_downloaded_update,
    is_newer_version,
    normalize_version,
    parse_version_tuple,
)


class _FakeResponse:
    def __init__(self, payload: bytes, *, headers: dict[str, str] | None = None) -> None:
        self._stream = io.BytesIO(payload)
        self.headers = headers or {}

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class UpdaterTests(unittest.TestCase):
    def test_version_helpers(self) -> None:
        self.assertEqual(normalize_version("v01.2.03"), "1.2.3")
        self.assertEqual(parse_version_tuple("0.2.0"), (0, 2, 0))
        self.assertTrue(is_newer_version("0.2.1", "0.2.0"))
        self.assertFalse(is_newer_version("0.2.0", "0.2.0"))

    def test_find_available_update_reads_latest_release(self) -> None:
        payload = {
            "tag_name": "v9.9.9",
            "html_url": "https://github.com/Balrog57/RomPatcher/releases/tag/v9.9.9",
            "published_at": "2026-03-29T12:00:00Z",
            "body": "Nouvelle version",
            "assets": [
                {
                    "name": "RomPatcher-9.9.9-win64.exe",
                    "browser_download_url": "https://example.com/RomPatcher-9.9.9-win64.exe",
                    "size": 123,
                }
            ],
        }
        response = _FakeResponse(json.dumps(payload).encode("utf-8"))

        with patch("rompatcher.updater.urllib.request.urlopen", return_value=response):
            release = find_available_update(current_version="0.2.0", force_refresh=True)

        self.assertIsNotNone(release)
        self.assertEqual(release.version, "9.9.9")
        self.assertEqual(release.asset.name, "RomPatcher-9.9.9-win64.exe")

    def test_download_release_asset_writes_file(self) -> None:
        release = ReleaseInfo(
            version="1.2.3",
            tag_name="v1.2.3",
            html_url="https://example.com/release",
            published_at="2026-03-29T12:00:00Z",
            body="",
            asset=ReleaseAsset(name="RomPatcher-1.2.3-win64.exe", download_url="https://example.com/file.exe", size=4),
        )
        destination = ROOT / ".tmp_tests" / "downloaded-update.exe"
        response = _FakeResponse(b"EXE!", headers={"Content-Length": "4"})

        with patch("rompatcher.updater.urllib.request.urlopen", return_value=response):
            downloaded = download_release_asset(release, destination=destination)

        self.assertEqual(downloaded.read_bytes(), b"EXE!")

    def test_build_windows_update_script_contains_expected_paths(self) -> None:
        script = build_windows_update_script(
            Path("C:/Temp/update.exe"),
            Path("C:/Apps/RomPatcher.exe"),
            process_id=4321,
        )
        content = script.read_text(encoding="utf-8")
        self.assertIn("C:/Apps/RomPatcher.exe", content.replace("\\", "/"))
        self.assertIn("4321", content)

    def test_install_downloaded_update_launches_cmd_script(self) -> None:
        downloaded = ROOT / ".tmp_tests" / "install-update.exe"
        downloaded.write_bytes(b"EXE")

        with patch("rompatcher.updater.subprocess.Popen") as popen_mock:
            script = install_downloaded_update(downloaded, current_exe=Path("C:/Apps/RomPatcher.exe"))

        popen_mock.assert_called_once()
        self.assertTrue(script.exists())
