from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .classify import bucket_for_path, classify_file
from .models import FileEntry, ImageResult, PartitionResult
from .tooling import (
    ensure_partitions_unpacked,
    ensure_raw_super,
    fingerprint_for_path,
    is_sparse_image,
    load_lpdump_json,
    log,
    run_cmd,
    safe_name,
)


def detect_filesystem_kind(file_type: str) -> Tuple[Optional[str], bool]:
    lower = file_type.lower()
    if "ext2 filesystem" in lower or "ext3 filesystem" in lower or "ext4 filesystem" in lower:
        return "ext", True
    if "erofs" in lower:
        return "erofs", False
    if "filesystem data" in lower and "linux rev 1.0" in lower:
        return "ext", True
    return None, False


def inspect_partition_type(img_path: Path, file_tool: str) -> str:
    output = run_cmd([file_tool, str(img_path)]).strip()
    if ":" in output:
        return output.split(":", 1)[1].strip()
    return output


def parse_dumpe2fs(img_path: Path, dumpe2fs: str) -> Tuple[Dict[str, int], bool]:
    output = run_cmd([dumpe2fs, "-h", str(img_path)])
    stats: Dict[str, int] = {}
    features: set[str] = set()
    interesting = {
        "Block count",
        "Reserved block count",
        "Free blocks",
        "Block size",
        "Inode count",
        "Free inodes",
    }
    for line in output.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key == "Filesystem features":
            features = set(value.strip().split())
            continue
        if key not in interesting:
            continue
        stats[key] = int(value.strip().split()[0])
    block_count = stats.get("Block count", 0)
    free_blocks = stats.get("Free blocks", 0)
    reserved_blocks = stats.get("Reserved block count", 0)
    block_size = stats.get("Block size", 0)
    inode_count = stats.get("Inode count", 0)
    free_inodes = stats.get("Free inodes", 0)
    return {
        "block_count": block_count,
        "free_blocks": free_blocks,
        "reserved_blocks": reserved_blocks,
        "block_size": block_size,
        "inode_count": inode_count,
        "free_inodes": free_inodes,
        "used_inodes": inode_count - free_inodes,
        "used_bytes": (block_count - free_blocks) * block_size,
        "free_bytes": free_blocks * block_size,
        "reserved_bytes": reserved_blocks * block_size,
    }, ("shared_blocks" in features)


def ensure_partition_extracted(img_path: Path, out_dir: Path, debugfs: str) -> None:
    marker = out_dir / ".rdump_complete"
    if marker.exists():
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    log(f"[extract] {img_path.name} -> {out_dir}")
    run_cmd(
        [debugfs, "-R", f"rdump / {out_dir}", str(img_path)],
        tolerate_debugfs_ownership_warnings=True,
    )
    marker.write_text("ok\n", encoding="utf-8")


def scan_partition_tree(partition: str, root_dir: Path, bucket_depth: int) -> Tuple[List[FileEntry], Dict[str, int], Dict[str, int]]:
    file_entries: List[FileEntry] = []
    category_totals: Dict[str, int] = defaultdict(int)
    bucket_totals: Dict[str, int] = defaultdict(int)

    for path in sorted(root_dir.rglob("*")):
        if path.name == ".rdump_complete" or path.is_dir():
            continue
        rel_path = path.relative_to(root_dir)
        try:
            size = path.lstat().st_size if path.is_symlink() else path.stat().st_size
        except FileNotFoundError:
            continue
        category = classify_file(rel_path)
        bucket = bucket_for_path(rel_path, depth=bucket_depth)
        entry = FileEntry(
            partition=partition,
            path=rel_path.as_posix(),
            size=size,
            category=category,
            bucket=bucket,
        )
        file_entries.append(entry)
        category_totals[category] += size
        bucket_totals[bucket] += size

    return file_entries, dict(category_totals), dict(bucket_totals)


def sort_totals_desc(totals: Dict[str, int]) -> Dict[str, int]:
    return dict(sorted(totals.items(), key=lambda item: (-item[1], item[0])))


def analyze_super_image(
    super_img: Path,
    workdir: Path,
    mode: str,
    tools: Dict[str, str],
    top_n: int,
    selected_partitions: Optional[Iterable[str]] = None,
    bucket_depth: int = 2,
) -> ImageResult:
    if not super_img.exists():
        raise FileNotFoundError(f"Missing super image: {super_img}")

    fingerprint = fingerprint_for_path(super_img)
    prefix = f"{fingerprint}_{safe_name(super_img.stem)}"
    raw_super = workdir / "raw" / f"{prefix}.raw"
    layout_path = workdir / "layout" / f"{prefix}_layout.json"
    unpack_dir = workdir / "unpacked" / prefix
    extract_root = workdir / "fs" / prefix

    sparse = is_sparse_image(super_img)
    raw_super = ensure_raw_super(super_img, raw_super, tools["simg2img"])
    layout = load_lpdump_json(raw_super, layout_path, tools["lpdump"])

    partitions_meta = {item["name"]: item for item in layout.get("partitions", [])}
    requested = sorted(set(selected_partitions or partitions_meta.keys()))
    warnings: List[str] = []
    unknown_requested = [name for name in requested if name not in partitions_meta]
    if unknown_requested:
        warnings.append(
            "Requested partition names were not found in super metadata: "
            + ", ".join(unknown_requested)
        )
    if mode == "full" and selected_partitions:
        warnings.append(
            "Full scan limited to selected partitions: " + ", ".join(requested)
        )

    if mode in {"summary", "full"}:
        ensure_partitions_unpacked(raw_super, unpack_dir, tools["lpunpack"])

    partition_results: List[PartitionResult] = []
    global_categories: Dict[str, int] = defaultdict(int)
    global_buckets: Dict[str, int] = defaultdict(int)
    global_files: List[FileEntry] = []

    for partition_name in sorted(partitions_meta):
        meta = partitions_meta[partition_name]
        result = PartitionResult(
            name=partition_name,
            group_name=meta.get("group_name", ""),
            declared_size=int(meta.get("size", 0)),
            is_dynamic=bool(meta.get("is_dynamic", False)),
            scan_mode="metadata",
        )

        img_path = unpack_dir / f"{partition_name}.img"
        if mode in {"summary", "full"} and img_path.exists():
            result.image_path = str(img_path)
            result.image_file_size = img_path.stat().st_size
            result.file_type = inspect_partition_type(img_path, tools["file"])
            fs_kind, fs_supported = detect_filesystem_kind(result.file_type)
            result.filesystem_kind = fs_kind
            result.filesystem_supported = fs_supported
            result.scan_mode = "summary"

            if fs_supported and fs_kind == "ext":
                result.filesystem_stats, result.shared_blocks_detected = parse_dumpe2fs(
                    img_path,
                    tools["dumpe2fs"],
                )
            elif fs_kind is not None:
                result.warnings.append(
                    f"Deep scan skipped for unsupported filesystem kind: {fs_kind}"
                )
            else:
                result.warnings.append("Filesystem type not recognized for deep scan")

            if mode == "full" and partition_name in requested:
                if fs_supported and fs_kind == "ext":
                    extract_dir = extract_root / partition_name
                    ensure_partition_extracted(img_path, extract_dir, tools["debugfs"])
                    files, category_totals, bucket_totals = scan_partition_tree(
                        partition_name,
                        extract_dir,
                        bucket_depth,
                    )
                    result.scan_mode = "full"
                    result.file_count = len(files)
                    result.apparent_size_total = sum(item.size for item in files)
                    result.category_totals = sort_totals_desc(category_totals)
                    result.bucket_totals = sort_totals_desc(bucket_totals)
                    result.top_files = sorted(files, key=lambda item: (-item.size, item.path))[:top_n]

                    if result.shared_blocks_detected:
                        used_bytes = result.filesystem_stats.get("used_bytes", 0)
                        apparent_total = result.apparent_size_total or 0
                        ratio = (apparent_total / used_bytes * 100.0) if used_bytes else 0.0
                        result.warnings.append(
                            "shared_blocks detected. Category totals, top buckets, and top files "
                            "use logical file sizes, not unique physical block usage. "
                            f"apparent_size_total={apparent_total} bytes, "
                            f"fs_used_bytes={used_bytes} bytes, ratio={ratio:.1f}%."
                        )

                    for key, value in category_totals.items():
                        global_categories[key] += value
                    for key, value in bucket_totals.items():
                        global_buckets[f"{partition_name}:{key}"] += value
                    global_files.extend(files)
                elif partition_name in requested:
                    result.warnings.append(
                        f"Requested full scan but partition '{partition_name}' is not supported for deep inspection"
                    )
        elif mode in {"summary", "full"}:
            result.warnings.append("Partition image not found after lpunpack")

        if result.warnings:
            warnings.extend(f"{partition_name}: {item}" for item in result.warnings)

        partition_results.append(result)

    super_device = layout.get("super_device", {})
    block_devices = layout.get("block_devices", [])
    block_size = int(block_devices[0].get("block_size", 0)) if block_devices else 0
    alignment = int(block_devices[0].get("alignment", 0)) if block_devices else 0
    total_size = int(super_device.get("total_size", 0))
    used_size = int(super_device.get("used_size", 0))
    free_size = total_size - used_size

    return ImageResult(
        schema_version="1.0",
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        mode=mode,
        input_super=str(super_img.resolve()),
        fingerprint=fingerprint,
        is_sparse=sparse,
        sparse_size=super_img.stat().st_size,
        raw_super=str(raw_super),
        raw_size=raw_super.stat().st_size,
        super_total_size=total_size,
        super_used_size=used_size,
        super_free_size=free_size,
        block_size=block_size,
        alignment=alignment,
        block_devices=block_devices,
        groups=layout.get("groups", []),
        resolved_tools=tools,
        selected_partitions=requested,
        partitions=partition_results,
        global_category_totals=sort_totals_desc(dict(global_categories)),
        global_bucket_totals=sort_totals_desc(dict(global_buckets)),
        global_top_files=sorted(global_files, key=lambda item: (-item.size, item.path))[:top_n],
        warnings=warnings,
    )
