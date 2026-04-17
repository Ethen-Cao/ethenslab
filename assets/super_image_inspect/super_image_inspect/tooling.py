from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional


SPARSE_MAGIC = 0xED26FF3A

DEFAULT_TOOL_CANDIDATES = {
    "simg2img": [
        "/home/voyah/workspace/aosp_code/out/host/linux-x86/bin/simg2img",
        "/home/voyah/workspace/8397/qssi/out/host/linux-x86/bin/simg2img",
    ],
    "lpdump": [
        "/home/voyah/workspace/aosp_code/out/host/linux-x86/bin/lpdump",
        "/home/voyah/workspace/8397/qssi/out/host/linux-x86/bin/lpdump",
    ],
    "lpunpack": [
        "/home/voyah/workspace/8397/qssi/out/host/linux-x86/bin/lpunpack",
        "/home/voyah/workspace/aosp_code/out/host/linux-x86/bin/lpunpack",
    ],
    "debugfs": [
        "/home/voyah/workspace/aosp_code/out/host/linux-x86/bin/debugfs",
        "/home/voyah/workspace/8397/qssi/out/host/linux-x86/bin/debugfs",
    ],
    "dumpe2fs": [
        "/usr/sbin/dumpe2fs",
        "/sbin/dumpe2fs",
    ],
    "file": [
        "/usr/bin/file",
    ],
}

TOOLS_BY_MODE = {
    "metadata": {"simg2img", "lpdump"},
    "summary": {"simg2img", "lpdump", "lpunpack", "file", "dumpe2fs"},
    "full": {"simg2img", "lpdump", "lpunpack", "file", "dumpe2fs", "debugfs"},
}


def log(message: str) -> None:
    print(message, file=sys.stderr)


def script_root() -> Path:
    return Path(__file__).resolve().parent.parent


def fingerprint_for_path(path: Path) -> str:
    payload = f"{path.resolve()}::{path.stat().st_size}::{path.stat().st_mtime_ns}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in name)


def resolve_tool(name: str, tool_dir: Optional[Path] = None) -> str:
    env_name = name.upper().replace("-", "_")
    if os.environ.get(env_name):
        return os.environ[env_name]

    search_dirs: List[Path] = []
    if tool_dir is not None:
        search_dirs.append(tool_dir.resolve())
        search_dirs.append((tool_dir / "tools").resolve())

    root = script_root()
    search_dirs.append(root)
    search_dirs.append(root / "tools")

    for directory in search_dirs:
        candidate = directory / name
        if candidate.exists():
            return str(candidate)

    from_path = shutil.which(name)
    if from_path:
        return from_path

    for candidate in DEFAULT_TOOL_CANDIDATES.get(name, []):
        if Path(candidate).exists():
            return candidate

    raise FileNotFoundError(f"Unable to locate required tool: {name}")


def resolve_tools(mode: str, tool_dir: Optional[Path] = None) -> Dict[str, str]:
    return {name: resolve_tool(name, tool_dir) for name in sorted(TOOLS_BY_MODE[mode])}


def run_cmd(
    args: List[str],
    *,
    tolerate_debugfs_ownership_warnings: bool = False,
) -> str:
    proc = subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    if proc.returncode != 0:
        if tolerate_debugfs_ownership_warnings:
            harmless = True
            for line in stderr.splitlines():
                if "Operation not permitted while changing ownership" in line:
                    continue
                if line.startswith("debugfs "):
                    continue
                if not line.strip():
                    continue
                harmless = False
                break
            if harmless:
                return stdout
        raise RuntimeError(
            "Command failed:\n"
            + " ".join(args)
            + "\nSTDOUT:\n"
            + stdout
            + "\nSTDERR:\n"
            + stderr
        )
    return stdout


def is_sparse_image(path: Path) -> bool:
    with path.open("rb") as handle:
        header = handle.read(4)
    if len(header) < 4:
        raise ValueError(f"Image is too small to inspect sparse header: {path}")
    return struct.unpack("<I", header)[0] == SPARSE_MAGIC


def ensure_raw_super(super_img: Path, raw_path: Path, simg2img: str) -> Path:
    if raw_path.exists() and raw_path.stat().st_mtime_ns >= super_img.stat().st_mtime_ns:
        return raw_path
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if is_sparse_image(super_img):
        log(f"[convert] {super_img} -> {raw_path}")
        run_cmd([simg2img, str(super_img), str(raw_path)])
    else:
        log(f"[reuse] raw image input: {super_img}")
        if raw_path.exists():
            raw_path.unlink()
        try:
            os.link(super_img, raw_path)
        except OSError:
            shutil.copy2(super_img, raw_path)
    return raw_path


def load_lpdump_json(raw_super: Path, layout_path: Path, lpdump: str) -> Dict[str, object]:
    if not layout_path.exists() or layout_path.stat().st_mtime_ns < raw_super.stat().st_mtime_ns:
        log(f"[layout] {raw_super} -> {layout_path}")
        output = run_cmd([lpdump, "-j", str(raw_super)])
        layout_path.parent.mkdir(parents=True, exist_ok=True)
        layout_path.write_text(output, encoding="utf-8")
    return json.loads(layout_path.read_text(encoding="utf-8"))


def ensure_partitions_unpacked(raw_super: Path, unpack_dir: Path, lpunpack: str) -> None:
    if unpack_dir.exists() and any(unpack_dir.glob("*.img")):
        return
    unpack_dir.mkdir(parents=True, exist_ok=True)
    log(f"[unpack] {raw_super} -> {unpack_dir}")
    run_cmd([lpunpack, str(raw_super), str(unpack_dir)])
