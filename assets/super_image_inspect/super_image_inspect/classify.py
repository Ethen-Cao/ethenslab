from __future__ import annotations

import os
from pathlib import Path


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
    ".yaml",
    ".yml",
}

MEDIA_SUFFIXES = {
    ".aac",
    ".gif",
    ".jpg",
    ".jpeg",
    ".mp3",
    ".mp4",
    ".ogg",
    ".png",
    ".wav",
    ".webm",
    ".webp",
}


def classify_file(path: Path) -> str:
    lower = path.name.lower()
    suffix = path.suffix.lower()
    rel = str(path).replace(os.sep, "/").lower()
    if suffix == ".model" or "/tts/" in rel or "/models/" in rel:
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


def bucket_for_path(path: Path, depth: int = 2) -> str:
    parts = [part for part in path.parts if part not in {"", "."}]
    if not parts:
        return "."
    depth = max(depth, 1)
    if len(parts) <= depth:
        return "/".join(parts)
    return "/".join(parts[:depth])

