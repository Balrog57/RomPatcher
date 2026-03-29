from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .version import APP_NAME, APP_VERSION

ProgressCallback = Callable[[float, str | None], None]

XDELTA_OWNER = "jmacd"
XDELTA_REPO = "xdelta-gpl"
XDELTA_RELEASES_URL = f"https://api.github.com/repos/{XDELTA_OWNER}/{XDELTA_REPO}/releases"


@dataclass(slots=True)
class DownloadableTool:
    name: str
    version: str
    tag_name: str
    download_url: str
    html_url: str
    size: int = 0


def _report(callback: ProgressCallback | None, value: float, message: str | None = None) -> None:
    if callback is not None:
        callback(max(0.0, min(1.0, float(value))), message)


def _api_request(url: str, *, timeout: int = 12) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{APP_NAME}/{APP_VERSION}",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def managed_tools_dir() -> Path:
    root = Path(os.getenv("LOCALAPPDATA", Path.home()))
    return root / "RomPatcherDesktop" / "tools"


def xdelta_install_path() -> Path:
    return managed_tools_dir() / "xdelta3.exe"


def find_xdelta_tool(*, timeout: int = 12) -> DownloadableTool:
    try:
        payload = _api_request(XDELTA_RELEASES_URL, timeout=timeout)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Impossible de contacter GitHub pour récupérer xdelta3 (HTTP {exc.code}).") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError("Impossible de contacter GitHub pour récupérer xdelta3.") from exc

    fallback: DownloadableTool | None = None
    for release in payload:
        if release.get("draft"):
            continue

        asset = None
        for candidate in release.get("assets") or []:
            name = str(candidate.get("name", "")).lower()
            if name.endswith("x86_64.exe.zip") and ".sign" not in name:
                asset = candidate
                break
        if asset is None:
            continue

        tool = DownloadableTool(
            name=str(asset.get("name", "")),
            version=str(release.get("name") or release.get("tag_name") or ""),
            tag_name=str(release.get("tag_name") or ""),
            download_url=str(asset.get("browser_download_url") or ""),
            html_url=str(release.get("html_url") or ""),
            size=int(asset.get("size", 0)),
        )

        release_label = f"{tool.version} {tool.tag_name}".lower()
        if not release.get("prerelease", False) and "beta" not in release_label:
            return tool
        if fallback is None:
            fallback = tool

    if fallback is not None:
        return fallback
    raise RuntimeError("Aucune release Windows xdelta3 compatible n'a été trouvée.")


def install_xdelta3(
    destination: Path | None = None,
    *,
    progress: ProgressCallback | None = None,
    timeout: int = 120,
) -> Path:
    tool = find_xdelta_tool(timeout=min(timeout, 20))
    final_path = destination or xdelta_install_path()
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_root = final_path.parent / f"rompatcher_xdelta_download_{uuid4().hex}"
    temp_root.mkdir(parents=True, exist_ok=True)
    zip_path = temp_root / tool.name
    request = urllib.request.Request(tool.download_url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})

    try:
        _report(progress, 0.05, "xdelta3 : téléchargement de l'archive")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response, zip_path.open("wb") as handle:
                total = int(response.headers.get("Content-Length", tool.size or 0))
                downloaded = 0
                block_size = 1024 * 128
                while True:
                    chunk = response.read(block_size)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        _report(progress, 0.05 + (downloaded / total) * 0.7, "xdelta3 : téléchargement en cours")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Téléchargement de xdelta3 impossible (HTTP {exc.code}).") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("Téléchargement de xdelta3 impossible.") from exc

        _report(progress, 0.8, "xdelta3 : extraction de l'exécutable")
        with zipfile.ZipFile(zip_path) as archive:
            exe_names = [name for name in archive.namelist() if name.lower().endswith(".exe")]
            if not exe_names:
                raise RuntimeError("Archive xdelta3 invalide : aucun exécutable trouvé.")
            target_name = next((name for name in exe_names if "xdelta3" in Path(name).name.lower()), exe_names[0])
            extracted = temp_root / Path(target_name).name
            extracted.write_bytes(archive.read(target_name))

        final_path.write_bytes(extracted.read_bytes())
        _report(progress, 1.0, "xdelta3 installé")
        return final_path
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


__all__ = [
    "DownloadableTool",
    "managed_tools_dir",
    "xdelta_install_path",
    "find_xdelta_tool",
    "install_xdelta3",
]
