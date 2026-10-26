#!/usr/bin/env python3
"""Automated quality gate verifier for /home/ethen/workspace/github/ethenslab/work/art-wiki/*.md."""

import os
import re
import sys
from pathlib import Path

WIKI_DIR = Path("/home/ethen/workspace/github/ethenslab/work/art-wiki")

SUPPORTED_MERMAID = (
    "flowchart ",
    "graph ",
    "sequenceDiagram",
    "stateDiagram-v2",
    "stateDiagram",
    "classDiagram",
    "erDiagram",
    "xychart-beta",
)

FILE_LINK_RE = re.compile(r"\]\((file:///[^)#\s]+)(?:#L(\d+)(?:-L?(\d+))?)?\)")
UNQUOTED_NODE_SPECIAL_RE = re.compile(r'\b[A-Za-z0-9_]+\[(?!")[^\]\n]*[()<>:/][^\]\n]*\]')
ALERT_RE = re.compile(r"^\s*>\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]")


def check_file(md_path: Path) -> list[str]:
    errors: list[str] = []
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if len(lines) < 250 and md_path.name != "README.md":
        errors.append(f"Too short ({len(lines)} lines < 250 expected)")

    # 1. Check required sections for mechanism wikis
    if md_path.name != "README.md":
        for kw in ("What", "Why", "How", "能利用这个机制做什么"):
            if kw not in text:
                errors.append(f"Missing required section keyword: {kw}")
        if "```mermaid" not in text:
            errors.append("Missing Mermaid diagram")
        if "```text" not in text and "┌" not in text and "+---" not in text:
            errors.append("Missing ASCII/Unicode structure diagram")

    # 2. Check file:// links and line ranges
    file_links = FILE_LINK_RE.findall(text)
    if len(file_links) < 5:
        errors.append(f"Too few file:// source links ({len(file_links)})")
    line_count_cache: dict[str, int] = {}
    for uri, l_start, l_end in file_links:
        fs_path = uri[len("file://") :]
        if not os.path.exists(fs_path):
            errors.append(f"Broken file link: {uri}")
            continue
        if os.path.isfile(fs_path) and l_start:
            if fs_path not in line_count_cache:
                with open(fs_path, "rb") as f:
                    line_count_cache[fs_path] = sum(1 for _ in f)
            max_line = line_count_cache[fs_path]
            s = int(l_start)
            e = int(l_end) if l_end else s
            if s < 1 or e > max_line + 5 or s > e:
                errors.append(
                    f"Out-of-range line link {uri}#L{l_start}"
                    + (f"-L{l_end}" if l_end else "")
                    + f" (file has {max_line} lines)"
                )

    # 3. Check Mermaid blocks & consecutive GitHub Alerts
    in_code = False
    in_mermaid = False
    mermaid_first_line_checked = False
    mermaid_type = ""
    prev_was_alert_block = False
    in_alert_block = False

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~~"):
            fence = stripped[:3]
            if not in_code:
                in_code = True
                if stripped.startswith("```mermaid"):
                    in_mermaid = True
                    mermaid_first_line_checked = False
                    mermaid_type = ""
            else:
                in_code = False
                in_mermaid = False
            in_alert_block = False
            continue

        if in_mermaid:
            if not stripped or stripped.startswith("%%"):
                continue
            if not mermaid_first_line_checked:
                mermaid_first_line_checked = True
                mermaid_type = stripped
                if not any(stripped.startswith(t) for t in SUPPORTED_MERMAID):
                    errors.append(f"Line {idx}: Unsupported Mermaid diagram header '{stripped}'")
            elif mermaid_type.startswith(("flowchart", "graph")):
                if UNQUOTED_NODE_SPECIAL_RE.search(stripped):
                    errors.append(
                        f"Line {idx}: Unquoted special chars in flowchart node label: {stripped}"
                    )
            continue

        if in_code:
            continue

        # Alert check outside code blocks
        if ALERT_RE.match(line):
            if prev_was_alert_block or in_alert_block:
                errors.append(f"Line {idx}: Consecutive or nested GitHub Alert")
            in_alert_block = True
        elif stripped.startswith(">"):
            # Continuation of blockquote / alert
            pass
        elif stripped == "":
            if in_alert_block:
                prev_was_alert_block = True
                in_alert_block = False
        else:
            prev_was_alert_block = False
            in_alert_block = False

    return errors


def main() -> int:
    targets = sorted(WIKI_DIR.glob("*.md"))
    if not targets:
        print(f"No markdown files found in {WIKI_DIR}")
        return 1

    total_errors = 0
    for md in targets:
        errs = check_file(md)
        line_cnt = sum(1 for _ in md.open("rb"))
        if errs:
            print(f"[WARN] {md.name} ({line_cnt} lines): {len(errs)} issue(s)")
            for e in errs:
                print(f"   - {e}")
            total_errors += len(errs)
        else:
            print(f"[PASS] {md.name} ({line_cnt} lines)")

    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
