#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
收集源码/配置文件到单一文本，便于 AI 分析。
安全增强：
- 跳过软链与非常规文件；防目录逃逸（realpath 仍须在扫描根内）
- 避免自吃输出（跳过正在写的输出文件）
- 默认排除常见密钥/证书等敏感后缀（可用 --unsafe 关闭）
- 更稳健二进制判定（NUL + 不可打印比例）
- 体量限流：--max-bytes, --max-files
功能增强：
- --types/-t 指定类型，仅收集匹配的文件（Yocto 配置/配方、脚本、Python 等）
- --list-types 查看可用类型与匹配规则
- --types-config 载入 JSON 扩展/覆盖类型映射（exts/names/patterns/shebangs）
"""

import os
import sys
import time
import json
import fnmatch
import argparse
import stat
from typing import Set, List, Dict, Tuple

# ----------------- 默认排除规则 -----------------
EXCLUDE_DIRS: Set[str] = {
    '.git', '__pycache__', 'node_modules', 'build',
    'dist', 'target', '.vscode', '.idea', 'venv', '.env'
}

EXCLUDE_EXTS: Set[str] = {
    # 编译产物
    '.pyc', '.pyo', '.o', '.so', '.a', '.dll', '.exe', '.class', '.jar',
    # 图片
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg', '.webp',
    # 音视频
    '.mp3', '.wav', '.mp4', '.mov', '.avi', '.mkv', '.flac',
    # 压缩/归档
    '.zip', '.tar', '.gz', '.rar', '.7z',
    '.xz', '.zst', '.zstd', '.lz4', '.lz', '.bz2', '.tgz', '.tbz', '.txz',
    # 文档和字体
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.eot', '.ttf', '.woff', '.woff2',
    # 数据库
    '.db', '.sqlite3'
}

# 敏感后缀（默认也排除，可用 --unsafe 关闭）
SENSITIVE_EXTS: Set[str] = {
    '.pem', '.der', '.crt', '.cer',
    '.key', '.pk8', '.p12', '.pfx',
    '.jks', '.keystore', '.asc', '.gpg'
}

# ----------------- 内置类型映射（可被 --types-config 覆写/扩展） -----------------
FILE_TYPE_GROUPS: Dict[str, Dict[str, List[str]]] = {
    # 典型 Yocto/BitBake 相关
    "yocto": {
        "exts": [".bb", ".bbappend", ".bbclass", ".inc", ".conf", ".wks", ".wic", ".wks.in"],
        "names": ["local.conf", "bblayers.conf", "layer.conf"],
        "patterns": ["conf/*.conf", "conf/*.inc", "*/conf/layer.conf", "*.bbmask"],
        "shebangs": []
    },
    # Shell 脚本
    "scripts": {
        "exts": [".sh", ".bash"],
        "names": [],
        "patterns": ["scripts/*", "*/scripts/*"],
        "shebangs": ["bash", "sh", "zsh"]
    },
    # Python
    "python": {
        "exts": [".py"],
        "names": [],
        "patterns": [],
        "shebangs": ["python"]
    },
    # CMake/Make
    "cmake": {
        "exts": [".cmake"],
        "names": ["CMakeLists.txt"],
        "patterns": [],
        "shebangs": []
    },
    "make": {
        "exts": [".mk"],
        "names": ["Makefile", "makefile", "GNUmakefile"],
        "patterns": [],
        "shebangs": []
    },
    # 补丁
    "patches": {
        "exts": [".patch", ".diff"],
        "names": [],
        "patterns": [],
        "shebangs": []
    },
    # 设备树
    "dts": {
        "exts": [".dts", ".dtsi"],
        "names": [],
        "patterns": [],
        "shebangs": []
    },
    # INI/CFG
    "ini": {
        "exts": [".ini", ".cfg"],
        "names": [],
        "patterns": [],
        "shebangs": []
    }
}

# ----------------- 工具函数 -----------------
def sanitize_for_header(s: str) -> str:
    """避免文件名中的控制字符破坏分隔结构。"""
    return s.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')

def looks_binary_by_chars(buf: bytes) -> bool:
    """启发式：不可打印字符占比过高视为二进制。"""
    if not buf:
        return False
    texty = sum((32 <= b <= 126) or b in (9, 10, 13) for b in buf)
    return (texty / len(buf)) < 0.85

def is_regular_file(path: str) -> bool:
    try:
        st = os.lstat(path)
        return stat.S_ISREG(st.st_mode)
    except Exception:
        return False

def is_symlink(path: str) -> bool:
    try:
        return os.path.islink(path)
    except Exception:
        return False

def is_binary(filepath: str, chunk_size: int = 4096) -> bool:
    """
    更宽松且更准确的文本判定：
    1) 若包含 NUL 直接认为二进制（UTF-16/32 BOM 豁免）。
    2) 否则尝试以 UTF-8 严格解码——能解码则视为文本。
    3) 严格解码失败时，再用“不可打印比例”启发式兜底。
    4) 读错/无权限等异常，保守当作二进制以避免卡死。
    """
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(chunk_size)
        if b'\x00' in chunk:
            if chunk.startswith((b'\xff\xfe', b'\xfe\xff', b'\xff\xfe\x00\x00', b'\x00\x00\xfe\xff')):
                return False
            return True
        # 尝试严格 UTF-8 解码
        chunk.decode('utf-8')   # 成功即是文本
        return False
    except UnicodeDecodeError:
        # 兜底：不可打印比例很高才当二进制（阈值放宽到 0.5）
        def looks_binary_by_chars(buf: bytes) -> bool:
            if not buf:
                return False
            texty = sum((32 <= b <= 126) or b in (9, 10, 13) for b in buf)
            return (texty / len(buf)) < 0.5
        return looks_binary_by_chars(chunk)
    except (IOError, PermissionError, OSError):
        return True


def read_shebang(filepath: str) -> str:
    """读取首行 shebang（若存在），返回小写字符串。"""
    try:
        with open(filepath, 'rb') as f:
            first = f.readline(256)
        if first.startswith(b'#!'):
            return first.decode('utf-8', errors='ignore').strip().lower()
    except Exception:
        pass
    return ""

def generate_output_filename(base_name: str) -> str:
    """如果输出文件已存在，则生成带时间戳的新文件名。"""
    if not os.path.exists(base_name):
        return base_name
    name, ext = os.path.splitext(base_name)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return f"{name}_{timestamp}{ext}"

def norm_ext(ext: str) -> str:
    """标准化后缀：小写 + 以 . 开头。"""
    ext = ext.strip()
    if not ext:
        return ext
    if not ext.startswith('.'):
        ext = '.' + ext
    return ext.lower()

def merge_type_groups(base: Dict[str, Dict[str, List[str]]],
                      override: Dict[str, Dict[str, List[str]]]) -> Dict[str, Dict[str, List[str]]]:
    """合并类型配置：支持覆写与扩展。"""
    result = {k: {kk: vv[:] for kk, vv in v.items()} for k, v in base.items()}
    for group, spec in override.items():
        if group not in result:
            result[group] = {"exts": [], "names": [], "patterns": [], "shebangs": []}
        dst = result[group]
        for key in ("exts", "names", "patterns", "shebangs"):
            vals = spec.get(key, [])
            if key == "exts":
                vals = [norm_ext(x) for x in vals]
            for x in vals:
                if x not in dst.setdefault(key, []):
                    dst[key].append(x)
    return result

def build_active_filters(groups: Dict[str, Dict[str, List[str]]],
                         selected: List[str]) -> Dict[str, Set[str]]:
    """构建合并后的过滤器（用于快速判断是否匹配）。"""
    filt_exts: Set[str] = set()
    filt_names: Set[str] = set()
    filt_patterns: Set[str] = set()
    filt_shebangs: Set[str] = set()
    for g in selected:
        spec = groups.get(g)
        if not spec:
            continue
        filt_exts.update(norm_ext(e) for e in spec.get("exts", []))
        filt_names.update(spec.get("names", []))
        filt_patterns.update(spec.get("patterns", []))
        filt_shebangs.update(s.lower() for s in spec.get("shebangs", []))
    return {
        "exts": filt_exts,
        "names": filt_names,
        "patterns": filt_patterns,
        "shebangs": filt_shebangs
    }

def file_matches_types(file_path: str, rel_header_path: str, filt: Dict[str, Set[str]]) -> bool:
    """仅用于过滤：判断文件是否匹配选中的类型规则。"""
    basename = os.path.basename(file_path)
    _, ext = os.path.splitext(basename)
    ext = ext.lower()

    if ext in filt["exts"]:
        return True
    if basename in filt["names"]:
        return True
    for pat in filt["patterns"]:
        if fnmatch.fnmatch(rel_header_path, pat) or fnmatch.fnmatch(basename, pat):
            return True
    if filt["shebangs"]:
        sb = read_shebang(file_path)
        if sb and any(tok in sb for tok in filt["shebangs"]):
            return True
    return False

def detect_matched_groups(file_path: str, rel_header_path: str,
                          all_groups: Dict[str, Dict[str, List[str]]]) -> List[str]:
    """仅用于展示：检测文件匹配的所有组名（用于输出标注）。"""
    basename = os.path.basename(file_path)
    _, ext = os.path.splitext(basename)
    ext = ext.lower()
    sb = read_shebang(file_path)

    matched: List[str] = []
    for g, spec in all_groups.items():
        exts = {norm_ext(e) for e in spec.get("exts", [])}
        names = set(spec.get("names", []))
        patterns = set(spec.get("patterns", []))
        shebangs = {s.lower() for s in spec.get("shebangs", [])}

        hit = False
        if ext in exts or basename in names:
            hit = True
        else:
            for pat in patterns:
                if fnmatch.fnmatch(rel_header_path, pat) or fnmatch.fnmatch(basename, pat):
                    hit = True
                    break
            if not hit and shebangs and sb:
                if any(tok in sb for tok in shebangs):
                    hit = True
        if hit:
            matched.append(g)
    return matched

def _build_abs_excludes_for_root(abs_root_dir: str, exclude_dirs: Set[str]) -> Set[str]:
    """
    将用户提供的排除目录映射为“针对该 root 的绝对前缀集合”：
    - 绝对路径：直接加入（及其 realpath）
    - 相对路径：与 root 拼接后加入（及其 realpath）
    都以末尾加 os.sep 的形式作为“前缀”做 startswith 判断。
    """
    out: Set[str] = set()
    for d in exclude_dirs:
        # 原样绝对/相对两路都考虑
        cands = []
        if os.path.isabs(d):
            cands.append(d)
        cands.append(os.path.join(abs_root_dir, d))

        for c in cands:
            try:
                p = os.path.abspath(c)
                out.add(p.rstrip(os.sep) + os.sep)
                rp = os.path.realpath(p)
                out.add(rp.rstrip(os.sep) + os.sep)
            except Exception:
                continue
    return out

# ----------------- 主收集逻辑 -----------------
def collect_files_to_single_file(
    root_dirs: List[str],
    output_filename: str,
    extra_exclude_dirs: List[str],
    selected_types: List[str],
    type_groups: Dict[str, Dict[str, List[str]]],
    max_bytes: int,
    max_files: int,
    unsafe: bool,
    quiet: bool
) -> None:
    """遍历目录，将符合条件的文本文件内容合并到一个输出文件。"""
    include_all_text = not selected_types
    active_filter = build_active_filters(type_groups, selected_types) if selected_types else None

    # 合并排除目录（目录名规则 + 用户规则）
    normalized_extra_excludes = {os.path.normpath(d.rstrip('/')) for d in extra_exclude_dirs}
    name_based_excludes = EXCLUDE_DIRS.union(normalized_extra_excludes)

    # 输出文件名与其绝对路径
    safe_output_filename = generate_output_filename(output_filename)
    safe_output_abs = os.path.abspath(safe_output_filename)

    # 有效后缀排除
    effective_exclude_exts = set(EXCLUDE_EXTS)
    if not unsafe:
        effective_exclude_exts |= SENSITIVE_EXTS

    file_count = 0

    try:
        with open(safe_output_filename, 'w', encoding='utf-8', errors='ignore') as outfile:
            for root_dir in root_dirs:
                abs_root_dir = os.path.abspath(root_dir)
                if not os.path.isdir(abs_root_dir):
                    if not quiet:
                        print(f"⚠️  跳过：目录 '{root_dir}' 不存在。")
                    continue

                real_root = os.path.realpath(abs_root_dir)
                # 针对该 root 的绝对排除前缀集合
                abs_exclude_prefixes = _build_abs_excludes_for_root(abs_root_dir, name_based_excludes)

                if not quiet:
                    print(f"\n📁 开始处理目录: {abs_root_dir}")

                for dirpath, dirnames, filenames in os.walk(abs_root_dir, topdown=True, followlinks=False):
                    # 目录层过滤：按目录名、绝对路径前缀、以及软链目录跳过
                    kept_dirnames = []
                    for d in dirnames:
                        full = os.path.join(dirpath, d)
                        # 名称排除
                        if d in name_based_excludes:
                            continue
                        # 绝对排除前缀
                        abs_full = os.path.abspath(full)
                        real_full = os.path.realpath(abs_full)
                        if any(abs_full.startswith(p) or real_full.startswith(p) for p in abs_exclude_prefixes):
                            continue
                        # 软链目录不进入
                        if is_symlink(full):
                            continue
                        kept_dirnames.append(d)
                    dirnames[:] = kept_dirnames  # 告诉 os.walk 不要深入被丢弃的目录

                    for filename in filenames:
                        # 限流：文件数量
                        if max_files and file_count >= max_files:
                            if not quiet:
                                print(f"⏹️ 达到 --max-files 限制（{max_files}），停止。")
                            return

                        file_path = os.path.join(dirpath, filename)

                        # 跳过输出文件自身
                        try:
                            if os.path.samefile(file_path, safe_output_abs):
                                continue
                        except Exception:
                            pass

                        # 仅处理常规文件；跳过软链
                        if not is_regular_file(file_path) or is_symlink(file_path):
                            continue

                        # 后缀排除（含敏感）
                        lname = filename.lower()
                        if any(lname.endswith(ext) for ext in effective_exclude_exts):
                            continue

                        # 真实路径必须仍在扫描根内（防目录逃逸）
                        real_file = os.path.realpath(file_path)
                        if not (real_file == real_root or real_file.startswith(real_root + os.sep)):
                            continue

                        # 二进制判定
                        if is_binary(file_path):
                            continue

                        try:
                            # header path 使用“相对项目根”的形式，避免泄露系统路径
                            relative_path = os.path.relpath(file_path, abs_root_dir)
                            header_path = sanitize_for_header(os.path.join(root_dir, relative_path).replace(os.sep, '/'))

                            # 类型过滤（当指定 --types 时）
                            if not include_all_text:
                                if not file_matches_types(file_path, header_path, active_filter):
                                    continue

                            # 展示用：标注匹配组
                            if include_all_text:
                                matched_str = "all-text"
                            else:
                                matched_groups = detect_matched_groups(file_path, header_path, type_groups)
                                matched_str = ", ".join(matched_groups) if matched_groups else "unknown"

                            # 写入头
                            outfile.write(f"--- 文件路径: {header_path}\n")
                            outfile.write(f"--- 文件类型: {matched_str}\n")
                            outfile.write(f"--- 文件开始 ---\n\n")

                            # 体量限流：按 max_bytes 读取
                            truncated = False
                            if max_bytes and max_bytes > 0:
                                # 先按字节读，粗暴但安全；编码按 utf-8 容错
                                with open(file_path, 'rb') as rb:
                                    data = rb.read(max_bytes + 1)
                                if len(data) > max_bytes:
                                    data = data[:max_bytes]
                                    truncated = True
                                text = data.decode('utf-8', errors='ignore')
                                outfile.write(text)
                            else:
                                with open(file_path, 'r', encoding='utf-8', errors='ignore') as infile:
                                    for line in infile:
                                        outfile.write(line)

                            if truncated:
                                outfile.write("\n\n--- ⏭ 内容已按 --max-bytes 截断 ---")

                            outfile.write("\n--- 文件结束 ---\n\n")
                            file_count += 1

                            if not quiet:
                                print(f"  ✅ 已添加: {relative_path}  ({matched_str})")

                        except Exception as e:
                            if not quiet:
                                print(f"  ❌ 错误：无法读取文件 {file_path}: {e}")

    except IOError as e:
        print(f"致命错误：无法写入到输出文件 {safe_output_filename}: {e}", file=sys.stderr)
        sys.exit(1)

    if not quiet:
        print("\n" + "="*60)
        print(f"🎉 处理完成！共 {file_count} 个文件被写入到 '{safe_output_filename}' 中。")
        print("="*60)

# ----------------- 配置加载/展示 -----------------
def load_types_config(path: str) -> Dict[str, Dict[str, List[str]]]:
    """加载外部 JSON 类型配置并合并。"""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError("类型配置必须是 JSON 对象（最外层字典）")
        normed: Dict[str, Dict[str, List[str]]] = {}
        for k, v in cfg.items():
            if not isinstance(v, dict):
                continue
            normed[k] = {
                "exts": [norm_ext(x) for x in v.get("exts", [])],
                "names": v.get("names", []),
                "patterns": v.get("patterns", []),
                "shebangs": v.get("shebangs", [])
            }
        return merge_type_groups(FILE_TYPE_GROUPS, normed)
    except Exception as e:
        print(f"⚠️  载入类型配置失败：{e}，改用内置类型。")
        return FILE_TYPE_GROUPS

def list_types(groups: Dict[str, Dict[str, List[str]]]) -> None:
    print("可用类型（--types 可选值）：\n")
    for name, spec in groups.items():
        print(f"[{name}]")
        print(f"  exts     : {', '.join(spec.get('exts', [])) or '-'}")
        print(f"  names    : {', '.join(spec.get('names', [])) or '-'}")
        print(f"  patterns : {', '.join(spec.get('patterns', [])) or '-'}")
        print(f"  shebangs : {', '.join(spec.get('shebangs', [])) or '-'}")
        print("")

# ----------------- 主入口 -----------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="将一个或多个目录下的源代码/配置合并为一个文本文件，用于 AI 代码分析（安全模式默认开启）。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("directories", nargs="*", default=["."],
                        help="要扫描的目录（默认：当前目录）")
    parser.add_argument("--output", "-o", default="combined_code.txt",
                        help="输出文件名（默认：combined_code.txt）")
    parser.add_argument("--exclude-dirs", "-e", nargs="+", default=[], metavar="DIR",
                        help="额外排除的目录名或路径（相对路径按每个扫描根解析）")
    parser.add_argument("--types", "-t", nargs="+", default=[],
                        help="指定收集的文件类型（如：yocto scripts python），不指定则收集所有文本文件")
    parser.add_argument("--list-types", action="store_true",
                        help="列出可用类型并退出")
    parser.add_argument("--types-config", default="",
                        help="JSON 文件路径，用于自定义类型映射（exts/names/patterns/shebangs）")
    parser.add_argument("--max-bytes", type=int, default=8*1024*1024,
                        help="单文件最大读取字节数（默认 8 MiB；0 表示不限制）")
    parser.add_argument("--max-files", type=int, default=0,
                        help="最多采集的文件数（默认 0=不限制）")
    parser.add_argument("--unsafe", action="store_true",
                        help="关闭敏感后缀屏蔽（.pem/.key/.pk8/.jks 等），慎用")
    parser.add_argument("--quiet", action="store_true",
                        help="静默模式，减少控制台输出")

    args = parser.parse_args()
    args.exclude_dirs = [os.path.normpath(p) for p in args.exclude_dirs]

    # 加载类型配置
    groups = load_types_config(args.types_config) if args.types_config else FILE_TYPE_GROUPS

    if args.list_types:
        list_types(groups)
        sys.exit(0)

    # 校验类型
    unknown = [t for t in args.types if t and t not in groups]
    if unknown:
        print(f"⚠️  未知类型：{', '.join(unknown)}。可用类型见 --list-types。将忽略未知类型。")
        args.types = [t for t in args.types if t in groups]

    collect_files_to_single_file(
        args.directories,
        args.output,
        args.exclude_dirs,
        args.types,
        groups,
        max_bytes=args.max_bytes,
        max_files=args.max_files,
        unsafe=args.unsafe,
        quiet=args.quiet
    )

if __name__ == '__main__':
    main()
