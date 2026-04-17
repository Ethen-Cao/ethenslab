# super_image_inspect Requirements

## 1. Background

CI and release engineering workflows need a generic, one-click tool to inspect a
single Android `super.img`. The tool must extract trustworthy metadata,
partition-level facts, and optional file-level summaries so that later tools can
build diff reports and historical trend analysis on top of a standardized
manifest.

The current gap is that most ad-hoc scripts are diff-oriented and hard-code
specific partition names or directory layouts. The new tool must treat
`super.img` as the primary input and work across different products as long as
standard Android host tools are available.


## 2. Goals

- Accept any single `super.img` path as input.
- Auto-detect whether the image is sparse or raw.
- Parse dynamic partition metadata without assuming fixed partition names.
- Produce a reusable machine-readable manifest for downstream diff/trend tools.
- Provide a human-readable Markdown report for direct inspection.
- Support layered analysis depth so users can trade accuracy for runtime.
- Avoid `mount` and avoid requiring root.


## 3. Non-Goals

- This tool does not compare two `super.img` files.
- This tool does not draw trend charts across builds.
- This tool does not modify or repack partition images.
- This tool does not guarantee deep parsing for every filesystem type in v1.


## 4. Primary Users

- Build and release engineers
- System image owners
- CI maintainers
- Performance and storage optimization engineers


## 5. Input and Invocation

### 5.1 Required Input

- One `super.img` file path

### 5.2 Optional Inputs

- Output work directory
- Analysis mode
- Top-N output size
- Partition filter list
- External tool directory
- Bucket depth for directory aggregation


## 6. Functional Requirements

### FR-1 Image-Level Inspection

The tool shall output the following image-level facts:

- input file path
- whether the image is sparse
- sparse file size
- raw image path and size after conversion if applicable
- super total size
- super used size
- super free size
- block size
- alignment
- block device metadata
- dynamic partition groups


### FR-2 Dynamic Partition Layout

The tool shall enumerate all logical partitions found in the `super.img`
metadata and output at least:

- partition name
- group name
- declared size
- dynamic flag
- corresponding unpacked image path if available
- unpacked image file size


### FR-3 Multi-Level Analysis Modes

The tool shall support the following modes:

- `metadata`
  - parse only super-level metadata
  - do not unpack logical partitions
- `summary`
  - unpack logical partitions
  - detect filesystem type
  - collect partition-level filesystem usage when supported
  - do not perform recursive file extraction
- `full`
  - include everything in `summary`
  - recursively inspect supported filesystem partitions
  - produce category summaries, bucket summaries, and top files


### FR-4 Filesystem Handling

The tool shall:

- support ext-family partition inspection in v1
- degrade gracefully for unsupported filesystems
- continue processing other partitions if one partition cannot be deeply parsed
- record warnings for unsupported or partially inspected partitions


### FR-5 File Classification

For partitions scanned in `full` mode, the tool shall classify files into
coarse categories including:

- `apk`
- `apex`
- `so`
- `jar`
- `oat_artifact`
- `kernel_module`
- `font`
- `media`
- `model_data`
- `config_data`
- `native_bin`
- `other`


### FR-6 Aggregation

For partitions scanned in `full` mode, the tool shall output:

- per-partition file count
- per-partition category totals
- per-partition top directories
- per-partition top files
- global category totals across scanned partitions
- global bucket totals across scanned partitions
- global top files across scanned partitions


### FR-7 Output Artifacts

The tool shall generate:

- `manifest.json`
- `summary.md`
- `partition_summary.csv`

When file-level scan is enabled, the tool shall additionally generate:

- `global_category_summary.csv`
- `partition_category_summary.csv`
- `global_bucket_summary.csv`
- `top_files.csv`


### FR-8 Standard Manifest

`manifest.json` shall be the canonical output for downstream automation and
shall contain:

- schema version
- generation timestamp
- resolved tool paths
- execution mode
- global warnings
- image-level metadata
- partition-level metadata
- filesystem statistics when available
- file-level aggregates when available


### FR-9 Caching and Reuse

The tool shall keep reusable intermediate artifacts under the work directory:

- converted raw super image
- lpdump JSON
- unpacked logical partition images
- extracted filesystem trees for deep inspection

The tool should reuse valid artifacts when rerun on the same input.


## 7. Non-Functional Requirements

### NFR-1 Genericity

- Must not hard-code partition names like `system`, `vendor`, or `product`
- Must work with arbitrary dynamic partition layouts
- Must not depend on a specific Android product output directory structure


### NFR-2 Reliability

- Failures in one partition should not invalidate the entire report when
  partial results can still be produced
- Every degraded behavior must be reported in warnings


### NFR-3 Observability

- Console output should show major phases:
  - conversion
  - metadata dump
  - unpack
  - per-partition scan
  - report generation


### NFR-4 Packaging

- The tool should work when bundled with external host binaries in the same
  directory
- Tool path override must be possible via environment variables and CLI


### NFR-5 Portability

- Implementation language: Python 3
- No third-party Python packages in v1


## 8. External Tool Dependencies

### Required in `metadata`

- `python3`
- `simg2img`
- `lpdump`

### Required in `summary`

- everything in `metadata`
- `lpunpack`
- `file`
- `dumpe2fs`

### Required in `full`

- everything in `summary`
- `debugfs`


## 9. Output Directory Layout

The work directory shall contain:

```text
<workdir>/
  raw/
  layout/
  unpacked/
  fs/
  reports/
```


## 10. CLI Requirements

The CLI shall support:

- positional `super_img`
- `--workdir`
- `--mode {metadata,summary,full}`
- `--top`
- `--partition` repeated
- `--tool-dir`
- `--bucket-depth`


## 11. Error Handling Requirements

The tool shall fail fast when:

- input `super.img` does not exist
- required tools for the requested mode are missing
- `lpdump` cannot parse the converted raw image

The tool shall continue with warnings when:

- a partition image cannot be deeply scanned
- a partition filesystem is unsupported
- file-level extraction is skipped for a filtered-out partition


## 12. Success Criteria for v1

The v1 delivery is successful if:

- it can inspect one real `super.img`
- it produces `manifest.json` and `summary.md`
- it reports all logical partitions from metadata
- it reports ext-family filesystem usage for supported partitions
- it outputs file-level summaries in `full` mode for supported partitions
- it does so without root and without mount

