from __future__ import annotations

import argparse
from pathlib import Path

from .analyzer import analyze_super_image
from .reporting import human_bytes, write_reports
from .tooling import resolve_tools


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect a single Android super.img.")
    parser.add_argument("super_img", type=Path, help="Path to the input super.img")
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("analysis_output"),
        help="Working directory for raw images, unpacked partitions, extracted files, and reports",
    )
    parser.add_argument(
        "--mode",
        choices=["metadata", "summary", "full"],
        default="full",
        help="Analysis depth. full is the most informative but also the most expensive",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=30,
        help="Top-N entries for bucket and file outputs",
    )
    parser.add_argument(
        "--partition",
        action="append",
        default=[],
        help="Limit deep full-scan to specific partition names. Can be repeated",
    )
    parser.add_argument(
        "--tool-dir",
        type=Path,
        default=None,
        help="Directory containing bundled host tools such as simg2img/lpdump/lpunpack/debugfs",
    )
    parser.add_argument(
        "--bucket-depth",
        type=int,
        default=2,
        help="Directory bucket depth used in full mode aggregation",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tools = resolve_tools(args.mode, args.tool_dir)
    workdir = args.workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    report = analyze_super_image(
        super_img=args.super_img.resolve(),
        workdir=workdir,
        mode=args.mode,
        tools=tools,
        top_n=args.top,
        selected_partitions=args.partition or None,
        bucket_depth=args.bucket_depth,
    )

    reports_dir = workdir / "reports"
    outputs = write_reports(report, reports_dir, args.top)

    print("super image inspect summary")
    print(f"mode             : {report.mode}")
    print(f"input super      : {report.input_super}")
    print(f"is sparse        : {report.is_sparse}")
    print(f"sparse size      : {report.sparse_size} ({human_bytes(report.sparse_size)})")
    print(f"raw size         : {report.raw_size} ({human_bytes(report.raw_size)})")
    print(f"super used size  : {report.super_used_size} ({human_bytes(report.super_used_size)})")
    print(f"super free size  : {report.super_free_size} ({human_bytes(report.super_free_size)})")
    print(f"partitions       : {len(report.partitions)}")
    if report.global_category_totals:
        print("top categories   :")
        for category, size in list(report.global_category_totals.items())[:8]:
            print(f"  {category}: {size} ({human_bytes(size)})")
    shared_blocks_count = sum(1 for item in report.partitions if item.shared_blocks_detected)
    full_shared_blocks_count = sum(
        1 for item in report.partitions if item.shared_blocks_detected and item.apparent_size_total is not None
    )
    if shared_blocks_count:
        print(f"shared_blocks   : {shared_blocks_count} partition(s) detected in filesystem metadata")
    if full_shared_blocks_count:
        print(
            "logical/physical: "
            f"{full_shared_blocks_count} full-scanned partition(s) may have apparent_size_total > fs_used_bytes"
        )
    if report.warnings:
        print(f"warnings         : {len(report.warnings)}")
    print("reports          :")
    for name, path in outputs.items():
        print(f"  {name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
