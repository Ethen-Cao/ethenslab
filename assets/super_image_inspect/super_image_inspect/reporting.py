from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from .models import FileEntry, ImageResult, PartitionResult


def human_bytes(num: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(num)
    for unit in units:
        if abs(value) < 1024.0 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{num} B"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def ranked_total_rows(totals: Dict[str, int], key_name: str) -> List[Dict[str, object]]:
    total = sum(totals.values())
    rows: List[Dict[str, object]] = []
    for key, value in sorted(totals.items(), key=lambda item: (-item[1], item[0])):
        share = (value / total * 100.0) if total else 0.0
        rows.append({key_name: key, "size": value, "share_percent": share})
    return rows


def partition_rows(partitions: Sequence[PartitionResult]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for item in partitions:
        stats = item.filesystem_stats
        rows.append(
            {
                "name": item.name,
                "group_name": item.group_name,
                "is_dynamic": item.is_dynamic,
                "declared_size": item.declared_size,
                "image_file_size": item.image_file_size,
                "file_type": item.file_type or "",
                "filesystem_kind": item.filesystem_kind or "",
                "filesystem_supported": item.filesystem_supported,
                "shared_blocks_detected": item.shared_blocks_detected,
                "fs_used_bytes": stats.get("used_bytes", 0),
                "fs_free_bytes": stats.get("free_bytes", 0),
                "fs_reserved_bytes": stats.get("reserved_bytes", 0),
                "file_count": item.file_count,
                "apparent_size_total": item.apparent_size_total,
                "scan_mode": item.scan_mode,
                "warning_count": len(item.warnings),
            }
        )
    return rows


def partition_category_rows(partitions: Sequence[PartitionResult]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for item in partitions:
        total = sum(item.category_totals.values())
        for category, size in item.category_totals.items():
            share = (size / total * 100.0) if total else 0.0
            rows.append(
                {
                    "partition": item.name,
                    "category": category,
                    "size": size,
                    "share_percent": share,
                }
            )
    rows.sort(key=lambda row: (row["partition"], -int(row["size"]), row["category"]))
    return rows


def partition_bucket_rows(partitions: Sequence[PartitionResult]) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for item in partitions:
        total = sum(item.bucket_totals.values())
        for bucket, size in item.bucket_totals.items():
            share = (size / total * 100.0) if total else 0.0
            rows.append(
                {
                    "partition": item.name,
                    "bucket": bucket,
                    "size": size,
                    "share_percent": share,
                }
            )
    rows.sort(key=lambda row: (row["partition"], -int(row["size"]), row["bucket"]))
    return rows


def top_file_rows(files: Iterable[FileEntry]) -> List[Dict[str, object]]:
    return [
        {
            "partition": item.partition,
            "path": item.path,
            "category": item.category,
            "bucket": item.bucket,
            "size": item.size,
        }
        for item in files
    ]


def write_csv(path: Path, rows: List[Dict[str, object]], columns: List[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def format_markdown_table(rows: List[Dict[str, object]], columns: List[Tuple[str, str]], limit: int | None = None) -> str:
    view = rows if limit is None else rows[:limit]
    header = "| " + " | ".join(title for _, title in columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body: List[str] = []
    for row in view:
        rendered: List[str] = []
        for key, _ in columns:
            value = row.get(key, "")
            if value is None:
                rendered.append("")
            elif isinstance(value, bool):
                rendered.append(str(value))
            elif isinstance(value, float):
                rendered.append(f"{value:.2f}")
            elif isinstance(value, int) and key not in {"warning_count", "file_count"}:
                rendered.append(f"{value} ({human_bytes(value)})")
            else:
                rendered.append(str(value))
        body.append("| " + " | ".join(rendered) + " |")
    return "\n".join([header, divider, *body]) if body else "\n".join([header, divider])


def write_manifest(report: ImageResult, reports_dir: Path) -> Path:
    ensure_dir(reports_dir)
    path = reports_dir / "manifest.json"
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path


def write_summary_md(report: ImageResult, reports_dir: Path, top_n: int) -> Path:
    ensure_dir(reports_dir)
    path = reports_dir / "summary.md"

    partition_summary = partition_rows(report.partitions)
    global_categories = ranked_total_rows(report.global_category_totals, "category")
    global_top_files = top_file_rows(report.global_top_files)
    shared_block_partitions = [
        item for item in report.partitions if item.shared_blocks_detected and item.apparent_size_total is not None
    ]
    category_partitions = [item for item in report.partitions if item.category_totals]
    bucket_partitions = [item for item in report.partitions if item.bucket_totals]

    lines = [
        "# super image inspect summary",
        "",
        "## Image",
        "",
        f"- Input super: `{report.input_super}`",
        f"- Mode: `{report.mode}`",
        f"- Fingerprint: `{report.fingerprint}`",
        f"- Sparse image: `{report.is_sparse}`",
        f"- Sparse size: `{report.sparse_size}` bytes ({human_bytes(report.sparse_size)})",
        f"- Raw size: `{report.raw_size}` bytes ({human_bytes(report.raw_size)})",
        f"- Super total size: `{report.super_total_size}` bytes ({human_bytes(report.super_total_size)})",
        f"- Super used size: `{report.super_used_size}` bytes ({human_bytes(report.super_used_size)})",
        f"- Super free size: `{report.super_free_size}` bytes ({human_bytes(report.super_free_size)})",
        f"- Block size: `{report.block_size}`",
        f"- Alignment: `{report.alignment}`",
        "",
        "## Groups",
        "",
    ]

    if report.groups:
        for item in report.groups:
            name = item.get("name", "")
            maximum = item.get("maximum_size", "")
            if maximum:
                lines.append(f"- `{name}` max=`{maximum}`")
            else:
                lines.append(f"- `{name}`")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Partitions",
            "",
            format_markdown_table(
                partition_summary,
                [
                    ("name", "partition"),
                    ("group_name", "group"),
                    ("declared_size", "declared_size"),
                    ("image_file_size", "image_file_size"),
                    ("filesystem_kind", "filesystem_kind"),
                    ("shared_blocks_detected", "shared_blocks_detected"),
                    ("apparent_size_total", "apparent_size_total"),
                    ("fs_used_bytes", "fs_used_bytes"),
                    ("file_count", "file_count"),
                    ("scan_mode", "scan_mode"),
                    ("warning_count", "warning_count"),
                ],
            ),
            "",
        ]
    )

    if shared_block_partitions:
        lines.extend(
            [
                "## Logical Vs Physical Notes",
                "",
                "- `shared_blocks_detected = True` means the filesystem reuses data blocks across files.",
                "- In these partitions, `apparent_size_total`, category totals, top buckets, and top files are logical file sizes.",
                "- Logical file sizes can exceed `fs_used_bytes`, because shared data blocks are counted once physically but may appear in multiple files logically.",
                "",
                format_markdown_table(
                    [
                        {
                            "partition": item.name,
                            "apparent_size_total": item.apparent_size_total,
                            "fs_used_bytes": item.filesystem_stats.get("used_bytes", 0),
                            "ratio_percent": (
                                (item.apparent_size_total / item.filesystem_stats.get("used_bytes", 1) * 100.0)
                                if item.filesystem_stats.get("used_bytes", 0)
                                and item.apparent_size_total is not None
                                else 0.0
                            ),
                        }
                        for item in shared_block_partitions
                    ],
                    [
                        ("partition", "partition"),
                        ("apparent_size_total", "apparent_size_total"),
                        ("fs_used_bytes", "fs_used_bytes"),
                        ("ratio_percent", "apparent_vs_used_%"),
                    ],
                ),
                "",
            ]
        )

    if report.global_category_totals:
        lines.extend(
            [
                "## Categories",
                "",
                "### Global",
                "",
                format_markdown_table(
                    global_categories,
                    [
                        ("category", "category"),
                        ("size", "size"),
                        ("share_percent", "share_%"),
                    ],
                ),
                "",
            ]
        )

    for item in category_partitions:
        lines.extend(
            [
                f"### {item.name}",
                "",
                format_markdown_table(
                    ranked_total_rows(item.category_totals, "category"),
                    [
                        ("category", "category"),
                        ("size", "size"),
                        ("share_percent", "share_%"),
                    ],
                ),
                "",
            ]
        )

    if bucket_partitions:
        lines.extend(
            [
                f"## Top {top_n} Buckets By Partition",
                "",
            ]
        )

    for item in bucket_partitions:
        lines.extend(
            [
                f"### {item.name}",
                "",
                format_markdown_table(
                    ranked_total_rows(item.bucket_totals, "bucket"),
                    [
                        ("bucket", "bucket"),
                        ("size", "size"),
                        ("share_percent", "share_%"),
                    ],
                    limit=top_n,
                ),
                "",
            ]
        )

    if report.global_top_files:
        lines.extend(
            [
                f"## Top {top_n} Files",
                "",
                format_markdown_table(
                    global_top_files,
                    [
                        ("partition", "partition"),
                        ("path", "path"),
                        ("category", "category"),
                        ("size", "size"),
                    ],
                    limit=top_n,
                ),
                "",
            ]
        )

    if report.warnings:
        lines.append("## Warnings")
        lines.append("")
        for warning in report.warnings:
            lines.append(f"- {warning}")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_reports(report: ImageResult, reports_dir: Path, top_n: int) -> Dict[str, Path]:
    ensure_dir(reports_dir)
    outputs = {
        "manifest": write_manifest(report, reports_dir),
        "summary": write_summary_md(report, reports_dir, top_n),
    }

    write_csv(
        reports_dir / "partition_summary.csv",
        partition_rows(report.partitions),
        [
            "name",
            "group_name",
            "is_dynamic",
            "declared_size",
            "image_file_size",
            "file_type",
            "filesystem_kind",
            "filesystem_supported",
            "shared_blocks_detected",
            "apparent_size_total",
            "fs_used_bytes",
            "fs_free_bytes",
            "fs_reserved_bytes",
            "file_count",
            "scan_mode",
            "warning_count",
        ],
    )
    outputs["partition_summary_csv"] = reports_dir / "partition_summary.csv"

    if report.global_category_totals:
        write_csv(
            reports_dir / "global_category_summary.csv",
            ranked_total_rows(report.global_category_totals, "category"),
            ["category", "size", "share_percent"],
        )
        outputs["global_category_summary_csv"] = reports_dir / "global_category_summary.csv"

        write_csv(
            reports_dir / "partition_category_summary.csv",
            partition_category_rows(report.partitions),
            ["partition", "category", "size", "share_percent"],
        )
        outputs["partition_category_summary_csv"] = reports_dir / "partition_category_summary.csv"

    if any(item.bucket_totals for item in report.partitions):
        write_csv(
            reports_dir / "partition_bucket_summary.csv",
            partition_bucket_rows(report.partitions),
            ["partition", "bucket", "size", "share_percent"],
        )
        outputs["partition_bucket_summary_csv"] = reports_dir / "partition_bucket_summary.csv"

    if report.global_bucket_totals:
        write_csv(
            reports_dir / "global_bucket_summary.csv",
            ranked_total_rows(report.global_bucket_totals, "bucket"),
            ["bucket", "size", "share_percent"],
        )
        outputs["global_bucket_summary_csv"] = reports_dir / "global_bucket_summary.csv"

    if report.global_top_files:
        write_csv(
            reports_dir / "top_files.csv",
            top_file_rows(report.global_top_files),
            ["partition", "path", "category", "bucket", "size"],
        )
        outputs["top_files_csv"] = reports_dir / "top_files.csv"

    return outputs
