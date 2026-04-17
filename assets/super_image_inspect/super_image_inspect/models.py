from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class FileEntry:
    partition: str
    path: str
    size: int
    category: str
    bucket: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "partition": self.partition,
            "path": self.path,
            "size": self.size,
            "category": self.category,
            "bucket": self.bucket,
        }


@dataclass
class PartitionResult:
    name: str
    group_name: str
    declared_size: int
    is_dynamic: bool
    image_path: Optional[str] = None
    image_file_size: int = 0
    file_type: Optional[str] = None
    filesystem_kind: Optional[str] = None
    filesystem_supported: bool = False
    shared_blocks_detected: bool = False
    filesystem_stats: Dict[str, int] = field(default_factory=dict)
    scan_mode: str = "metadata"
    file_count: int = 0
    apparent_size_total: Optional[int] = None
    category_totals: Dict[str, int] = field(default_factory=dict)
    bucket_totals: Dict[str, int] = field(default_factory=dict)
    top_files: List[FileEntry] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "group_name": self.group_name,
            "declared_size": self.declared_size,
            "is_dynamic": self.is_dynamic,
            "image_path": self.image_path,
            "image_file_size": self.image_file_size,
            "file_type": self.file_type,
            "filesystem_kind": self.filesystem_kind,
            "filesystem_supported": self.filesystem_supported,
            "shared_blocks_detected": self.shared_blocks_detected,
            "filesystem_stats": self.filesystem_stats,
            "scan_mode": self.scan_mode,
            "file_count": self.file_count,
            "apparent_size_total": self.apparent_size_total,
            "category_totals": self.category_totals,
            "bucket_totals": self.bucket_totals,
            "top_files": [item.to_dict() for item in self.top_files],
            "warnings": self.warnings,
        }


@dataclass
class ImageResult:
    schema_version: str
    generated_at_utc: str
    mode: str
    input_super: str
    fingerprint: str
    is_sparse: bool
    sparse_size: int
    raw_super: str
    raw_size: int
    super_total_size: int
    super_used_size: int
    super_free_size: int
    block_size: int
    alignment: int
    block_devices: List[Dict[str, Any]]
    groups: List[Dict[str, Any]]
    resolved_tools: Dict[str, str]
    selected_partitions: List[str]
    partitions: List[PartitionResult]
    global_category_totals: Dict[str, int] = field(default_factory=dict)
    global_bucket_totals: Dict[str, int] = field(default_factory=dict)
    global_top_files: List[FileEntry] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at_utc": self.generated_at_utc,
            "mode": self.mode,
            "input_super": self.input_super,
            "fingerprint": self.fingerprint,
            "is_sparse": self.is_sparse,
            "sparse_size": self.sparse_size,
            "raw_super": self.raw_super,
            "raw_size": self.raw_size,
            "super_total_size": self.super_total_size,
            "super_used_size": self.super_used_size,
            "super_free_size": self.super_free_size,
            "block_size": self.block_size,
            "alignment": self.alignment,
            "block_devices": self.block_devices,
            "groups": self.groups,
            "resolved_tools": self.resolved_tools,
            "selected_partitions": self.selected_partitions,
            "partitions": [item.to_dict() for item in self.partitions],
            "global_category_totals": self.global_category_totals,
            "global_bucket_totals": self.global_bucket_totals,
            "global_top_files": [item.to_dict() for item in self.global_top_files],
            "warnings": self.warnings,
        }
