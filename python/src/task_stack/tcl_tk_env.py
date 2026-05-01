"""Point Tcl/Tk at a real install when the interpreter embeds broken paths (e.g. uv standalone builds on macOS)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _brew_prefix_tcl_tk() -> str | None:
    brew = shutil.which("brew")
    if not brew:
        return None
    try:
        out = subprocess.run(
            [brew, "--prefix", "tcl-tk"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    path = out.stdout.strip()
    return path or None


def _version_major_from_name(dirname: str, prefix: str) -> str | None:
    if not dirname.startswith(prefix) or len(dirname) <= len(prefix):
        return None
    rest = dirname[len(prefix) :]
    if not rest[0].isdigit():
        return None
    return rest.split(".", maxsplit=1)[0]


def _match_tcl_tk_under_lib(lib: Path) -> tuple[Path, Path] | None:
    """Pair Tcl and Tk script dirs (8.x or 9.x; Homebrew recently ships tcl9.0/tk9.0)."""
    if not lib.is_dir():
        return None
    tcl_paths: list[tuple[Path, str]] = []
    for p in lib.glob("tcl*/init.tcl"):
        if p.is_file():
            d = p.parent
            mj = _version_major_from_name(d.name, "tcl")
            if mj:
                tcl_paths.append((d, mj))
    tk_paths: list[tuple[Path, str]] = []
    for p in lib.glob("tk*/tk.tcl"):
        if p.is_file():
            d = p.parent
            mj = _version_major_from_name(d.name, "tk")
            if mj:
                tk_paths.append((d, mj))
    if not tcl_paths or not tk_paths:
        return None

    def by_major_then_name(
        paths: list[tuple[Path, str]],
        *,
        prefer_eight: bool,
    ) -> list[tuple[Path, str]]:
        def sort_key(item: tuple[Path, str]) -> tuple[int, str]:
            _path, mj = item
            if prefer_eight:
                return (0 if mj == "8" else 1, item[0].name)
            return (0 if mj != "8" else 1, item[0].name)

        return sorted(paths, key=sort_key)

    # Prefer Tcl/Tk 8 when both exist (typical CPython _tkinter); else use 9 (current Homebrew default).
    for prefer_eight in (True, False):
        for tcl_path, tm in by_major_then_name(tcl_paths, prefer_eight=prefer_eight):
            for tk_path, km in by_major_then_name(tk_paths, prefer_eight=prefer_eight):
                if tm == km:
                    return (tcl_path, tk_path)
    return None


def _tcl_tk_roots_darwin() -> list[Path]:
    roots: list[Path] = []
    bp = _brew_prefix_tcl_tk()
    if bp:
        roots.append(Path(bp))
    roots.extend(
        [
            Path("/opt/homebrew/opt/tcl-tk"),
            Path("/usr/local/opt/tcl-tk"),
            Path("/opt/local"),
        ]
    )
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = str(r.resolve()) if r.exists() else str(r)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _existing_env_ok() -> bool:
    tcl = os.environ.get("TCL_LIBRARY")
    tk = os.environ.get("TK_LIBRARY")
    if not tcl or not tk:
        return False
    return (Path(tcl) / "init.tcl").is_file() and (Path(tk) / "tk.tcl").is_file()


def ensure_tcl_tk_env() -> None:
    if sys.platform != "darwin":
        return
    if _existing_env_ok():
        return
    for root in _tcl_tk_roots_darwin():
        pair = _match_tcl_tk_under_lib(root / "lib")
        if pair:
            os.environ["TCL_LIBRARY"] = str(pair[0])
            os.environ["TK_LIBRARY"] = str(pair[1])
            return
