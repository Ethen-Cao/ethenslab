# super_image_inspect Architecture

## 1. Scope

This document describes the v1 architecture for a single-image Android
`super.img` inspection tool. The design follows the requirements in
`docs/requirements.md` and intentionally separates:

- host tool resolution
- image/partition analysis
- classification logic
- report generation


## 2. Design Principles

- Use `super.img` as the only required input.
- Keep the machine-readable manifest as the system of record.
- Separate metadata collection from expensive file-level inspection.
- Degrade gracefully on unsupported filesystem types.
- Keep the implementation dependency-light and server-friendly.


## 3. High-Level Flow

```text
CLI
  -> Resolve required tools for selected mode
  -> Convert sparse super to raw if needed
  -> Dump logical partition metadata via lpdump
  -> Optionally unpack logical partition images via lpunpack
  -> For each partition:
       -> detect filesystem type
       -> collect filesystem stats if supported
       -> optionally extract filesystem tree and scan files
  -> Aggregate partition-level and global statistics
  -> Write manifest + markdown + csv outputs
```


## 4. Module Layout

```text
super_image_inspect/
  __init__.py
  __main__.py
  analyzer.py
  classify.py
  models.py
  reporting.py
  tooling.py
pyproject.toml
docs/
  requirements.md
  architecture.md
```


## 5. Module Responsibilities

### 5.1 `tooling.py`

Responsibilities:

- resolve external binaries
- choose required tools based on mode
- run subprocesses
- detect sparse image header
- convert sparse super to raw
- dump `lpdump` JSON
- unpack partition images

Why separate it:

- tool lookup and command execution are operational concerns, not business logic
- later packaging or environment changes can stay isolated here


### 5.2 `classify.py`

Responsibilities:

- categorize files by suffix/path heuristics
- compute directory bucket keys

Why separate it:

- classification rules are likely to evolve
- future versions can replace hard-coded rules with config-driven rules


### 5.3 `models.py`

Responsibilities:

- define internal dataclasses for:
  - file records
  - partition results
  - image-level manifest
- provide predictable serialization into JSON-friendly dictionaries


### 5.4 `analyzer.py`

Responsibilities:

- orchestrate image and partition analysis
- detect filesystem type
- parse `dumpe2fs` output for ext-family partitions
- extract ext-family partitions with `debugfs`
- scan extracted files and compute aggregates
- build the in-memory `ImageResult`

This is the core domain module.


### 5.5 `reporting.py`

Responsibilities:

- convert internal results into ranked rows
- write CSV files
- write Markdown summaries
- write canonical `manifest.json`


### 5.6 `__main__.py`

Responsibilities:

- parse CLI arguments
- select analysis mode
- invoke analyzer
- emit console summary


## 6. Data Model

### 6.1 `ImageResult`

Top-level report object containing:

- input image path
- sparse/raw facts
- super metadata
- partition results
- global aggregates
- warnings
- resolved tools


### 6.2 `PartitionResult`

Per-partition object containing:

- metadata from `lpdump`
- unpacked image path and size
- detected filesystem type
- filesystem statistics if supported
- scan mode actually executed
- per-partition warnings
- file-level aggregates when available


### 6.3 `FileEntry`

Represents one scanned file:

- partition name
- relative path
- size
- category
- bucket


## 7. Filesystem Strategy

### 7.1 Supported in v1

- ext-family images

Implementation:

- detect with `file`
- get usage stats via `dumpe2fs`
- extract and traverse with `debugfs rdump`


### 7.2 Unsupported or Partial in v1

- erofs
- other filesystem types

Behavior:

- keep partition-level metadata
- keep unpacked image size
- record warning
- skip file-level aggregation


## 8. Modes and Cost Model

### `metadata`

- cheapest
- no `lpunpack`
- no per-partition filesystem inspection

### `summary`

- medium cost
- unpack partition images
- collect filesystem type and ext usage stats
- no recursive file extraction

### `full`

- highest cost
- includes recursive extraction and file-level scan
- intended for detailed inspection and later diff baselines


## 9. Caching Layout

Caching is workdir-scoped and keyed by a stable fingerprint derived from:

- absolute input path
- file size
- file modification timestamp

This avoids collisions when multiple `super.img` files share the same basename.

Cached directories:

- `raw/<fingerprint>_*.raw`
- `layout/<fingerprint>_layout.json`
- `unpacked/<fingerprint>/`
- `fs/<fingerprint>/<partition>/`


## 10. Output Design

### Canonical Output

- `reports/manifest.json`

Why:

- downstream diff and trend tools should consume a stable schema rather than
  scrape Markdown

### Human Output

- `reports/summary.md`

Why:

- engineers need a readable summary for one-off inspection

### Spreadsheet-Friendly Output

- `reports/partition_summary.csv`
- `reports/global_category_summary.csv`
- `reports/partition_category_summary.csv`
- `reports/global_bucket_summary.csv`
- `reports/top_files.csv`


## 11. Genericity Strategy

The design is made generic by:

- enumerating partitions directly from `lpdump`
- separating mode-specific required tools
- avoiding product-specific paths
- making partition deep-scan optional and filterable
- writing all downstream logic against a standard manifest


## 12. Extension Points

The architecture intentionally leaves room for:

- erofs readers
- configurable classification rules
- manifest-to-diff tooling
- CI trend aggregation
- threshold-based alerts
- package-level inspection for APK internals


## 13. Risks

- `debugfs rdump` can be slow on large partitions
- unsupported filesystems limit deep analysis
- bundled host tools may still require compatible shared libraries
- full mode can consume large disk space for extracted files

Mitigation:

- keep layered modes
- reuse cache
- surface warnings in both console and manifest

