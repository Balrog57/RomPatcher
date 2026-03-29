from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import webbrowser
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from .version import APP_NAME, APP_VERSION, GITHUB_OWNER, GITHUB_RELEASES_URL, GITHUB_REPO

ProgressCallback = Callable[[float, str | None], None]


@dataclass(slots=True)
class ReleaseAsset:
    name: str
    download_url: str
    size: int = 0


@dataclass(slots=True)
class ReleaseInfo:
    version: str
    tag_name: str
    html_url: str
    published_at: str
    body: str
    asset: ReleaseAsset | None = None


def normalize_version(value: str) -> str:
    cleaned = value.strip().lower()
    if cleaned.startswith("v"):
        cleaned = cleaned[1:]
    parts = [part for part in cleaned.split(".") if part != ""]
    if not parts or any(not part.isdigit() for part in parts):
        raise ValueError(f"Version sémantique invalide : {value}")
    return ".".join(str(int(part)) for part in parts)


def parse_version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in normalize_version(value).split("."))


def is_newer_version(candidate: str, current: str = APP_VERSION) -> bool:
    return parse_version_tuple(candidate) > parse_version_tuple(current)


def is_frozen_build() -> bool:
    return bool(getattr(sys, "frozen", False)) and Path(sys.executable).suffix.lower() == ".exe"


def running_executable_path() -> Path | None:
    if not is_frozen_build():
        return None
    return Path(sys.executable)


def update_cache_path() -> Path:
    root = Path(os.getenv("LOCALAPPDATA", Path.home()))
    return root / "RomPatcherDesktop" / "update_state.json"


def _save_release_cache(release: ReleaseInfo) -> None:
    cache_path = update_cache_path()
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(release)
        payload["cached_at"] = int(time.time())
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return


def _load_release_cache(*, max_age_seconds: int) -> ReleaseInfo | None:
    cache_path = update_cache_path()
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    cached_at = int(payload.get("cached_at", 0))
    if int(time.time()) - cached_at > max_age_seconds:
        return None
    return _release_from_payload(payload)


def _report(callback: ProgressCallback | None, value: float, message: str | None = None) -> None:
    if callback is not None:
        callback(max(0.0, min(1.0, float(value))), message)


def _api_request(url: str, *, timeout: int = 8) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_NAME}/{APP_VERSION}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _release_from_payload(payload: dict[str, Any]) -> ReleaseInfo | None:
    tag_name = str(payload.get("tag_name") or payload.get("version") or "").strip()
    if not tag_name:
        return None

    version = normalize_version(tag_name)
    asset_payload = None
    assets = payload.get("assets") or []
    cached_asset = payload.get("asset")
    if isinstance(cached_asset, dict) and cached_asset:
        assets = [cached_asset]
    for candidate in assets:
        name = str(candidate.get("name", ""))
        if name.lower().endswith(".exe") and "rompatcher" in name.lower():
            asset_payload = candidate
            break

    asset = None
    if asset_payload:
        asset = ReleaseAsset(
            name=str(asset_payload.get("name", "")),
            download_url=str(asset_payload.get("browser_download_url") or asset_payload.get("download_url") or ""),
            size=int(asset_payload.get("size", 0)),
        )

    return ReleaseInfo(
        version=version,
        tag_name=tag_name,
        html_url=str(payload.get("html_url", GITHUB_RELEASES_URL)),
        published_at=str(payload.get("published_at", "")),
        body=str(payload.get("body", "")),
        asset=asset,
    )


def get_latest_release(*, force_refresh: bool = False, timeout: int = 8, cache_seconds: int = 43200) -> ReleaseInfo:
    if not force_refresh:
        cached = _load_release_cache(max_age_seconds=cache_seconds)
        if cached is not None:
            return cached

    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    try:
        payload = _api_request(url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Impossible de vérifier les mises à jour (HTTP {exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Impossible de contacter GitHub pour vérifier les mises à jour.") from exc

    release = _release_from_payload(payload)
    if release is None:
        raise RuntimeError("Réponse GitHub invalide pour la dernière release.")
    _save_release_cache(release)
    return release


def find_available_update(*, current_version: str = APP_VERSION, force_refresh: bool = False, timeout: int = 8) -> ReleaseInfo | None:
    release = get_latest_release(force_refresh=force_refresh, timeout=timeout)
    if is_newer_version(release.version, current_version):
        return release
    return None


def download_release_asset(
    release: ReleaseInfo,
    destination: Path | None = None,
    *,
    progress: ProgressCallback | None = None,
    timeout: int = 120,
) -> Path:
    if release.asset is None or not release.asset.download_url:
        raise RuntimeError("Aucun exécutable n'est attaché à cette release.")

    if destination is None:
        safe_name = release.asset.name or f"RomPatcher-{release.version}.exe"
        destination = Path(tempfile.gettempdir()) / safe_name

    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(
        release.asset.download_url,
        headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, destination.open("wb") as handle:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            block_size = 1024 * 256
            while True:
                chunk = response.read(block_size)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    _report(progress, downloaded / total, f"Téléchargement {downloaded // 1024} / {total // 1024} Ko")
    except urllib.error.URLError as exc:
        raise RuntimeError("Téléchargement de la mise à jour impossible.") from exc

    _report(progress, 1.0, "Téléchargement terminé")
    return destination


def build_windows_update_script(downloaded_exe: Path, current_exe: Path, *, process_id: int, relaunch: bool = True) -> Path:
    script_path = Path(tempfile.gettempdir()) / f"rompatcher-update-{process_id}.cmd"
    launch_line = f'start "" "{current_exe}"' if relaunch else "rem pas de relance"
    content = (
        "@echo off\n"
        "setlocal\n"
        f'set "CURRENT={current_exe}"\n'
        f'set "UPDATE={downloaded_exe}"\n'
        f'set "BACKUP={current_exe}.bak"\n'
        ":waitloop\n"
        f'tasklist /FI "PID eq {process_id}" | find "{process_id}" >nul\n'
        "if not errorlevel 1 (\n"
        "  timeout /t 1 /nobreak >nul\n"
        "  goto waitloop\n"
        ")\n"
        'copy /Y "%CURRENT%" "%BACKUP%" >nul 2>nul\n'
        'copy /Y "%UPDATE%" "%CURRENT%" >nul\n'
        f"{launch_line}\n"
        'del "%UPDATE%" >nul 2>nul\n'
        'del "%~f0" >nul 2>nul\n'
    )
    script_path.write_text(content, encoding="utf-8", newline="\r\n")
    return script_path


def install_downloaded_update(downloaded_exe: Path, *, current_exe: Path | None = None, relaunch: bool = True) -> Path:
    target = current_exe or running_executable_path()
    if target is None:
        raise RuntimeError("L'installation automatique n'est disponible que depuis l'exécutable Windows.")

    script_path = build_windows_update_script(downloaded_exe, target, process_id=os.getpid(), relaunch=relaunch)
    subprocess.Popen(["cmd.exe", "/c", str(script_path)], close_fds=True)
    return script_path


def open_releases_page(url: str | None = None) -> None:
    webbrowser.open(url or GITHUB_RELEASES_URL)


__all__ = [
    "ReleaseAsset",
    "ReleaseInfo",
    "normalize_version",
    "parse_version_tuple",
    "is_newer_version",
    "is_frozen_build",
    "running_executable_path",
    "get_latest_release",
    "find_available_update",
    "download_release_asset",
    "build_windows_update_script",
    "install_downloaded_update",
    "open_releases_page",
]
