#!/usr/bin/env python3
"""Compare two Android super images and attribute size growth."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import struct
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


SPARSE_MAGIC = 0xED26FF3A

TOOL_CANDIDATES = {
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

CONFIG_SUFFIXES = {
    ".avbpubkey",
    ".cil",
    ".cfg",
    ".conf",
    ".csv",
    ".der",
    ".ini",
    ".json",
    ".pb",
    ".pem",
    ".prop",
    ".rc",
    ".rsa",
    ".sha1",
    ".sha256",
    ".txt",
    ".xml",
    ".yml",
    ".yaml",
}
MEDIA_SUFFIXES = {
    ".aac",
    ".gif",
    ".jpg",
    ".jpeg",
    ".mp4",
    ".mp3",
    ".ogg",
    ".png",
    ".wav",
    ".webm",
    ".webp",
}


@dataclass
class FileEntry:
    partition: str
    relative_path: str
    size: int
    category: str
    bucket: str


@dataclass
class ImageAnalysis:
    label: str
    input_super: Path
    sparse_size: int
    raw_super: Path
    lpdump_json: Dict[str, object]
    partition_sizes: Dict[str, int]
    partition_fs_stats: Dict[str, Dict[str, int]]
    partition_types: Dict[str, str]
    file_map: Dict[Tuple[str, str], FileEntry]
    category_totals: Dict[str, int]
    bucket_totals: Dict[str, int]

    @property
    def used_size(self) -> int:
        super_device = self.lpdump_json.get("super_device", {})
        return int(super_device.get("used_size", 0))

    @property
    def total_size(self) -> int:
        super_device = self.lpdump_json.get("super_device", {})
        return int(super_device.get("total_size", 0))


def log(message: str) -> None:
    print(message, file=sys.stderr)


def human_bytes(num: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(num)
    for unit in units:
        if abs(value) < 1024.0 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{num} B"


def resolve_tool(name: str) -> str:
    env_name = name.upper().replace("-", "_")
    if env_name in os.environ and os.environ[env_name]:
        return os.environ[env_name]
    which = shutil.which(name)
    if which:
        return which
    for candidate in TOOL_CANDIDATES.get(name, []):
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(f"Unable to locate required tool: {name}")


def run_cmd(
    args: List[str],
    *,
    cwd: Optional[Path] = None,
    stdout_path: Optional[Path] = None,
    tolerate_ownership_warnings: bool = False,
) -> str:
    stdout_handle = None
    try:
        if stdout_path is not None:
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            stdout_handle = stdout_path.open("w", encoding="utf-8")
        proc = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            stdout=stdout_handle if stdout_handle else subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    finally:
        if stdout_handle is not None:
            stdout_handle.close()

    stderr = proc.stderr or ""
    stdout = "" if stdout_path else (proc.stdout or "")
    if proc.returncode != 0:
        if tolerate_ownership_warnings:
            harmless = True
            for line in stderr.splitlines():
                if not line:
                    continue
                if "Operation not permitted while changing ownership" in line:
                    continue
                if "debugfs " in line:
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
        magic = struct.unpack("<I", handle.read(4))[0]
    return magic == SPARSE_MAGIC


def ensure_raw_super(super_img: Path, raw_path: Path, simg2img: str) -> Path:
    if raw_path.exists() and raw_path.stat().st_mtime >= super_img.stat().st_mtime:
        return raw_path
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if is_sparse_image(super_img):
        log(f"[convert] {super_img.name} -> {raw_path}")
        run_cmd([simg2img, str(super_img), str(raw_path)])
    else:
        log(f"[reuse] raw super image detected: {super_img}")
        if raw_path.exists():
            raw_path.unlink()
        os.link(super_img, raw_path)
    return raw_path


def load_lpdump(raw_path: Path, out_json: Path, lpdump: str) -> Dict[str, object]:
    if not out_json.exists() or out_json.stat().st_mtime < raw_path.stat().st_mtime:
        log(f"[layout] dumping metadata for {raw_path.name}")
        output = run_cmd([lpdump, "-j", str(raw_path)])
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(output, encoding="utf-8")
    return json.loads(out_json.read_text(encoding="utf-8"))


def partition_sizes_from_layout(layout: Dict[str, object]) -> Dict[str, int]:
    sizes: Dict[str, int] = {}
    for item in layout.get("partitions", []):
        sizes[item["name"]] = int(item["size"])
    return sizes


def ensure_partitions_unpacked(raw_path: Path, out_dir: Path, lpunpack: str) -> None:
    if out_dir.exists() and any(out_dir.glob("*.img")):
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"[unpack] {raw_path.name} -> {out_dir}")
    run_cmd([lpunpack, str(raw_path), str(out_dir)])


def inspect_partition_type(img_path: Path, file_tool: str) -> str:
    output = run_cmd([file_tool, str(img_path)]).strip()
    if ":" in output:
        return output.split(":", 1)[1].strip()
    return output


def parse_dumpe2fs(img_path: Path, dumpe2fs: str) -> Dict[str, int]:
    output = run_cmd([dumpe2fs, "-h", str(img_path)])
    stats: Dict[str, int] = {}
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().split()[0]
        if key in {
            "Block count",
            "Reserved block count",
            "Free blocks",
            "Block size",
            "Inode count",
            "Free inodes",
        }:
            stats[key] = int(value)
    block_count = stats.get("Block count", 0)
    reserved_blocks = stats.get("Reserved block count", 0)
    free_blocks = stats.get("Free blocks", 0)
    block_size = stats.get("Block size", 0)
    stats["used_bytes"] = (block_count - free_blocks) * block_size
    stats["reserved_bytes"] = reserved_blocks * block_size
    stats["free_bytes"] = free_blocks * block_size
    stats["block_size_bytes"] = block_size
    return stats


def ensure_partition_extracted(img_path: Path, out_dir: Path, debugfs: str) -> None:
    marker = out_dir / ".rdump_complete"
    if marker.exists():
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"[extract] {img_path.name} -> {out_dir}")
    run_cmd(
        [debugfs, "-R", f"rdump / {out_dir}", str(img_path)],
        tolerate_ownership_warnings=True,
    )
    marker.write_text("ok\n", encoding="utf-8")


def classify_file(path: Path) -> str:
    lower = path.name.lower()
    suffix = path.suffix.lower()
    rel = str(path).replace(os.sep, "/").lower()
    if suffix == ".model" or "/tts/" in rel:
        return "model_data"
    if suffix == ".apk":
        return "apk"
    if suffix == ".apex":
        return "apex"
    if suffix == ".so":
        return "so"
    if suffix == ".jar":
        return "jar"
    if suffix in {".odex", ".vdex", ".art"}:
        return "oat_artifact"
    if suffix == ".ko":
        return "kernel_module"
    if suffix in {".ttf", ".otf"}:
        return "font"
    if suffix in MEDIA_SUFFIXES:
        return "media"
    if suffix in CONFIG_SUFFIXES:
        return "config_data"
    if "/bin/" in rel or "/xbin/" in rel:
        return "native_bin"
    if lower.endswith(".rc"):
        return "config_data"
    return "other"


def bucket_for_path(path: Path) -> str:
    parts = [part for part in path.parts if part not in {".", ""}]
    if not parts:
        return "."
    if len(parts) == 1:
        return parts[0]
    return "/".join(parts[:2])


def scan_partition_tree(partition: str, root_dir: Path) -> Tuple[Dict[Tuple[str, str], FileEntry], Dict[str, int], Dict[str, int]]:
    files: Dict[Tuple[str, str], FileEntry] = {}
    category_totals: Dict[str, int] = defaultdict(int)
    bucket_totals: Dict[str, int] = defaultdict(int)
    for dirpath, _, filenames in os.walk(root_dir):
        base = Path(dirpath)
        for filename in filenames:
            if filename == ".rdump_complete":
                continue
            path = base / filename
            rel_path = path.relative_to(root_dir)
            try:
                if path.is_symlink():
                    size = os.lstat(path).st_size
                else:
                    size = path.stat().st_size
            except FileNotFoundError:
                continue
            category = classify_file(rel_path)
            bucket = bucket_for_path(rel_path)
            entry = FileEntry(
                partition=partition,
                relative_path=rel_path.as_posix(),
                size=size,
                category=category,
                bucket=bucket,
            )
            files[(partition, entry.relative_path)] = entry
            category_totals[category] += size
            bucket_totals[f"{partition}:{bucket}"] += size
    return files, dict(category_totals), dict(bucket_totals)


def merge_totals(items: Iterable[Dict[str, int]]) -> Dict[str, int]:
    merged: Dict[str, int] = defaultdict(int)
    for item in items:
        for key, value in item.items():
            merged[key] += value
    return dict(merged)


def analyze_super_image(
    label: str,
    super_img: Path,
    root_workdir: Path,
    tools: Dict[str, str],
    partitions_to_extract: Optional[Iterable[str]] = None,
) -> ImageAnalysis:
    sparse_size = super_img.stat().st_size
    raw_path = root_workdir / "raw" / f"{label}_super.raw"
    raw_path = ensure_raw_super(super_img, raw_path, tools["simg2img"])

    layout_path = root_workdir / "layout" / f"{label}_layout.json"
    layout = load_lpdump(raw_path, layout_path, tools["lpdump"])
    partition_sizes = partition_sizes_from_layout(layout)

    unpack_dir = root_workdir / "unpacked" / label
    ensure_partitions_unpacked(raw_path, unpack_dir, tools["lpunpack"])

    wanted = set(partition_sizes)
    if partitions_to_extract is not None:
        wanted &= set(partitions_to_extract)

    partition_fs_stats: Dict[str, Dict[str, int]] = {}
    partition_types: Dict[str, str] = {}
    file_maps: List[Dict[Tuple[str, str], FileEntry]] = []
    category_totals: List[Dict[str, int]] = []
    bucket_totals: List[Dict[str, int]] = []

    for img_path in sorted(unpack_dir.glob("*.img")):
        partition = img_path.stem
        file_type = inspect_partition_type(img_path, tools["file"])
        partition_types[partition] = file_type
        if "filesystem" not in file_type.lower():
            continue
        partition_fs_stats[partition] = parse_dumpe2fs(img_path, tools["dumpe2fs"])
        if partition not in wanted:
            continue
        extract_dir = root_workdir / "fs" / label / partition
        ensure_partition_extracted(img_path, extract_dir, tools["debugfs"])
        file_map, cats, buckets = scan_partition_tree(partition, extract_dir)
        file_maps.append(file_map)
        category_totals.append(cats)
        bucket_totals.append(buckets)

    merged_files: Dict[Tuple[str, str], FileEntry] = {}
    for file_map in file_maps:
        merged_files.update(file_map)

    return ImageAnalysis(
        label=label,
        input_super=super_img,
        sparse_size=sparse_size,
        raw_super=raw_path,
        lpdump_json=layout,
        partition_sizes=partition_sizes,
        partition_fs_stats=partition_fs_stats,
        partition_types=partition_types,
        file_map=merged_files,
        category_totals=merge_totals(category_totals),
        bucket_totals=merge_totals(bucket_totals),
    )


def build_partition_rows(old: ImageAnalysis, new: ImageAnalysis) -> List[Dict[str, object]]:
    names = sorted(set(old.partition_sizes) | set(new.partition_sizes))
    rows: List[Dict[str, object]] = []
    super_delta = new.used_size - old.used_size
    for name in names:
        old_size = old.partition_sizes.get(name, 0)
        new_size = new.partition_sizes.get(name, 0)
        delta = new_size - old_size
        old_used = old.partition_fs_stats.get(name, {}).get("used_bytes", 0)
        new_used = new.partition_fs_stats.get(name, {}).get("used_bytes", 0)
        used_delta = new_used - old_used
        rows.append(
            {
                "partition": name,
                "old_size": old_size,
                "new_size": new_size,
                "delta": delta,
                "old_fs_used": old_used,
                "new_fs_used": new_used,
                "fs_used_delta": used_delta,
                "share_of_super_delta": (delta / super_delta * 100.0) if super_delta else 0.0,
            }
        )
    rows.sort(key=lambda item: abs(int(item["delta"])), reverse=True)
    return rows


def build_totals_rows(old_totals: Dict[str, int], new_totals: Dict[str, int], key_name: str) -> List[Dict[str, object]]:
    keys = sorted(set(old_totals) | set(new_totals))
    rows: List[Dict[str, object]] = []
    for key in keys:
        old_size = old_totals.get(key, 0)
        new_size = new_totals.get(key, 0)
        rows.append(
            {
                key_name: key,
                "old_size": old_size,
                "new_size": new_size,
                "delta": new_size - old_size,
            }
        )
    rows.sort(key=lambda item: abs(int(item["delta"])), reverse=True)
    return rows


def build_file_rows(old: ImageAnalysis, new: ImageAnalysis) -> List[Dict[str, object]]:
    keys = sorted(set(old.file_map) | set(new.file_map))
    rows: List[Dict[str, object]] = []
    for key in keys:
        old_entry = old.file_map.get(key)
        new_entry = new.file_map.get(key)
        old_size = old_entry.size if old_entry else 0
        new_size = new_entry.size if new_entry else 0
        category = new_entry.category if new_entry else old_entry.category
        rows.append(
            {
                "partition": key[0],
                "path": key[1],
                "category": category,
                "old_size": old_size,
                "new_size": new_size,
                "delta": new_size - old_size,
            }
        )
    rows.sort(key=lambda item: abs(int(item["delta"])), reverse=True)
    return rows


def write_csv(path: Path, rows: List[Dict[str, object]], columns: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def format_markdown_table(rows: List[Dict[str, object]], columns: List[Tuple[str, str]], limit: Optional[int] = None) -> str:
    view = rows if limit is None else rows[:limit]
    header = "| " + " | ".join(title for _, title in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body: List[str] = []
    for row in view:
        rendered: List[str] = []
        for key, _ in columns:
            value = row.get(key, "")
            if isinstance(value, float):
                rendered.append(f"{value:.2f}")
            elif isinstance(value, int) and key.endswith(("size", "delta", "used")):
                rendered.append(f"{value} ({human_bytes(value)})")
            else:
                rendered.append(str(value))
        body.append("| " + " | ".join(rendered) + " |")
    return "\n".join([header, divider, *body])


def write_markdown_report(
    path: Path,
    old: ImageAnalysis,
    new: ImageAnalysis,
    partition_rows: List[Dict[str, object]],
    category_rows: List[Dict[str, object]],
    bucket_rows: List[Dict[str, object]],
    file_rows: List[Dict[str, object]],
    top_n: int,
) -> None:
    super_sparse_delta = new.sparse_size - old.sparse_size
    super_used_delta = new.used_size - old.used_size
    top_partition = partition_rows[0]["partition"] if partition_rows else "n/a"
    top_partition_delta = partition_rows[0]["delta"] if partition_rows else 0

    lines = [
        "# super.img diff report",
        "",
        "## Summary",
        "",
        f"- Old super: `{old.input_super}`",
        f"- New super: `{new.input_super}`",
        f"- Sparse file delta: `{super_sparse_delta}` bytes ({human_bytes(super_sparse_delta)})",
        f"- Raw used_size delta: `{super_used_delta}` bytes ({human_bytes(super_used_delta)})",
        f"- Largest partition contributor: `{top_partition}` ({human_bytes(int(top_partition_delta))})",
        "",
        "## Partition layout diff",
        "",
        format_markdown_table(
            partition_rows,
            [
                ("partition", "partition"),
                ("old_size", "old_size"),
                ("new_size", "new_size"),
                ("delta", "delta"),
                ("old_fs_used", "old_fs_used"),
                ("new_fs_used", "new_fs_used"),
                ("fs_used_delta", "fs_used_delta"),
                ("share_of_super_delta", "share_of_super_delta_%"),
            ],
        ),
        "",
        "## Category diff",
        "",
        format_markdown_table(
            category_rows,
            [
                ("category", "category"),
                ("old_size", "old_size"),
                ("new_size", "new_size"),
                ("delta", "delta"),
            ],
        ),
        "",
        "## Directory bucket diff",
        "",
        format_markdown_table(
            bucket_rows,
            [
                ("bucket", "bucket"),
                ("old_size", "old_size"),
                ("new_size", "new_size"),
                ("delta", "delta"),
            ],
            limit=top_n,
        ),
        "",
        f"## Top {top_n} file deltas",
        "",
        format_markdown_table(
            file_rows,
            [
                ("partition", "partition"),
                ("path", "path"),
                ("category", "category"),
                ("old_size", "old_size"),
                ("new_size", "new_size"),
                ("delta", "delta"),
            ],
            limit=top_n,
        ),
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def choose_partitions_to_extract(old_layout: Dict[str, int], new_layout: Dict[str, int], extract_all: bool) -> List[str]:
    names = sorted(set(old_layout) | set(new_layout))
    if extract_all:
        return names
    changed = [name for name in names if old_layout.get(name, 0) != new_layout.get(name, 0)]
    return changed or names


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two Android super.img files.")
    parser.add_argument("old_super", type=Path, help="Older super.img path")
    parser.add_argument("new_super", type=Path, help="Newer super.img path")
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("analysis_short_term"),
        help="Workspace for raw images, unpacked partitions, extracted files, and reports",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=30,
        help="Number of directory and file deltas to keep in reports",
    )
    parser.add_argument(
        "--all-partitions",
        action="store_true",
        help="Extract and scan all logical partitions instead of only changed ones",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tools = {name: resolve_tool(name) for name in TOOL_CANDIDATES}

    workdir = args.workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    old_super = args.old_super.resolve()
    new_super = args.new_super.resolve()

    if not old_super.exists():
        raise FileNotFoundError(f"Missing old super image: {old_super}")
    if not new_super.exists():
        raise FileNotFoundError(f"Missing new super image: {new_super}")

    old_preview = analyze_super_image(
        "old",
        old_super,
        workdir,
        tools,
        partitions_to_extract=[],
    )
    new_preview = analyze_super_image(
        "new",
        new_super,
        workdir,
        tools,
        partitions_to_extract=[],
    )

    partitions_to_extract = choose_partitions_to_extract(
        old_preview.partition_sizes,
        new_preview.partition_sizes,
        args.all_partitions,
    )
    log("[plan] extracting/scanning partitions: " + ", ".join(partitions_to_extract))

    old = analyze_super_image(
        "old",
        old_super,
        workdir,
        tools,
        partitions_to_extract=partitions_to_extract,
    )
    new = analyze_super_image(
        "new",
        new_super,
        workdir,
        tools,
        partitions_to_extract=partitions_to_extract,
    )

    partition_rows = build_partition_rows(old, new)
    category_rows = build_totals_rows(old.category_totals, new.category_totals, "category")
    bucket_rows = build_totals_rows(old.bucket_totals, new.bucket_totals, "bucket")
    file_rows = build_file_rows(old, new)

    reports_dir = workdir / "reports"
    write_csv(
        reports_dir / "partition_diff.csv",
        partition_rows,
        [
            "partition",
            "old_size",
            "new_size",
            "delta",
            "old_fs_used",
            "new_fs_used",
            "fs_used_delta",
            "share_of_super_delta",
        ],
    )
    write_csv(
        reports_dir / "category_diff.csv",
        category_rows,
        ["category", "old_size", "new_size", "delta"],
    )
    write_csv(
        reports_dir / "bucket_diff.csv",
        bucket_rows,
        ["bucket", "old_size", "new_size", "delta"],
    )
    write_csv(
        reports_dir / "file_diff_top.csv",
        file_rows[: args.top],
        ["partition", "path", "category", "old_size", "new_size", "delta"],
    )

    summary = {
        "old_super": str(old_super),
        "new_super": str(new_super),
        "sparse_size_old": old.sparse_size,
        "sparse_size_new": new.sparse_size,
        "sparse_size_delta": new.sparse_size - old.sparse_size,
        "used_size_old": old.used_size,
        "used_size_new": new.used_size,
        "used_size_delta": new.used_size - old.used_size,
        "partitions_scanned": partitions_to_extract,
        "partition_diff": partition_rows,
        "category_diff": category_rows,
        "bucket_diff_top": bucket_rows[: args.top],
        "file_diff_top": file_rows[: args.top],
    }
    (reports_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown_report(
        reports_dir / "summary.md",
        old,
        new,
        partition_rows,
        category_rows,
        bucket_rows,
        file_rows,
        args.top,
    )

    print("super.img diff summary")
    print(f"old sparse size : {old.sparse_size} ({human_bytes(old.sparse_size)})")
    print(f"new sparse size : {new.sparse_size} ({human_bytes(new.sparse_size)})")
    print(f"sparse delta    : {new.sparse_size - old.sparse_size} ({human_bytes(new.sparse_size - old.sparse_size)})")
    print(f"old used_size   : {old.used_size} ({human_bytes(old.used_size)})")
    print(f"new used_size   : {new.used_size} ({human_bytes(new.used_size)})")
    print(f"used_size delta : {new.used_size - old.used_size} ({human_bytes(new.used_size - old.used_size)})")
    print("")
    print("top partition deltas")
    for row in partition_rows[: min(6, len(partition_rows))]:
        print(
            f"  {row['partition']}: delta={row['delta']} ({human_bytes(int(row['delta']))}), "
            f"fs_used_delta={row['fs_used_delta']} ({human_bytes(int(row['fs_used_delta']))})"
        )
    print("")
    print("top category deltas")
    for row in category_rows[: min(8, len(category_rows))]:
        print(f"  {row['category']}: {row['delta']} ({human_bytes(int(row['delta']))})")
    print("")
    print(f"reports written to: {reports_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
