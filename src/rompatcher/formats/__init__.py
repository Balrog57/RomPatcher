from __future__ import annotations

from pathlib import Path

from ..exceptions import UnsupportedPatchFormatError
from .aps import APSGBAPatch, APSN64Patch
from .base import BasePatch
from .bps import BPSPatch
from .external import BSDiffPatch, VCDiffPatch
from .ips import IPSPatch
from .ppf import PPFPatch
from .rup import RUPPatch
from .ups import UPSPatch


def parse_patch_bytes(data: bytes, path: Path | None = None) -> BasePatch:
    header = data[:8]
    extension = path.suffix.lower() if path is not None else ""

    if header.startswith(b"PATCH"):
        return IPSPatch.from_bytes(data, path)
    if header.startswith(b"UPS1"):
        return UPSPatch.from_bytes(data, path)
    if header.startswith(b"BPS1"):
        return BPSPatch.from_bytes(data, path)
    if header.startswith(b"NINJA2"):
        return RUPPatch.from_bytes(data, path)
    if header.startswith(b"APS10"):
        return APSN64Patch.from_bytes(data, path)
    if header.startswith(b"APS1"):
        return APSGBAPatch.from_bytes(data, path)
    if header.startswith(b"PPF"):
        return PPFPatch.from_bytes(data, path)
    if header.startswith(b"BSDIFF40") or extension in {".bspatch", ".bdf"}:
        return BSDiffPatch.from_bytes(data, path)
    if data[:3] == b"\xD6\xC3\xC4" or extension in {".xdelta", ".vcdiff"}:
        return VCDiffPatch.from_bytes(data, path)

    raise UnsupportedPatchFormatError(
        f"Format de patch non reconnu{f' pour {path.name}' if path else ''}."
    )
