#!/usr/bin/python3
# -*- coding: utf-8 -*-

"""
收集源码/配置文件到单一文本，便于 AI 分析。
安全增强：
- 跳过软链与非常规文件；防目录逃逸（realpath 仍须在扫描根内）
- 避免自吃输出（跳过正在写的输出文件）
- 默认排除常见密钥/证书等敏感后缀（可用 --unsafe 关闭）
- 更稳健二进制判定（NUL + UTF-8 探测 + 字符密度启发式）
- 体量限流：--max-bytes, --max-files
功能增强：
- 支持混合输入：可同时指定目录（递归扫描）和文件（直接添加）
- --types/-t 指定类型，仅收集匹配的文件
- --list-types 查看可用类型与匹配规则
- --types-config 载入 JSON 扩展/覆盖类型映射
"""

import os
import sys
import time
import json
import fnmatch
import argparse
import stat
from typing import Set, List, Dict, Tuple, Optional

# ----------------- 默认排除规则 -----------------
EXCLUDE_DIRS: Set[str] = {
    '.git', '__pycache__', 'node_modules', 
    'dist','.vscode', '.idea', 'venv', '.env',
    # 'target',
    # 'build'
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
        "exts": [".dts", ".dtsi",".dtso"],
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
    },
    # qnx_build_files
    "qnx_build_files": {
        "exts": [".ini", ".cfg",".tmpl",".build",".mk",".cmake",".sh", ".bash",".py"],
        "names": [],
        "patterns": [],
        "shebangs": ["bash", "sh", "zsh","python"]
    },
}

# ----------------- 工具函数 -----------------
def sanitize_for_header(s: str) -> str:
    return s.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')

def looks_binary_by_chars(buf: bytes, threshold: float = 0.85) -> bool:
    """
    启发式：检查 buffer 中文本字符的占比。
    如果 (文本字符数 / 总字节数) < threshold，则视为二进制。
    """
    if not buf:
        return False
    # 文本字符：32-126 (ASCII 可打印), 9 (\t), 10 (\n), 13 (\r)
    texty = sum((32 <= b <= 126) or b in (9, 10, 13) for b in buf)
    return (texty / len(buf)) < threshold

def is_binary(filepath: str, chunk_size: int = 4096) -> bool:
    """
    判断文件是否为二进制文件。
    策略：
    1. NUL 字节检查 (忽略 BOM)。
    2. UTF-8 严格解码尝试。
    3. 失败则回退到字符密度检测 (阈值降低到 0.5)。
    """
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(chunk_size)
        
        # 1. 包含 NUL 字节通常意味着二进制，但要排除 UTF-16/32 BOM 的情况
        if b'\x00' in chunk:
            # 常见的 BOM 头
            if chunk.startswith((b'\xff\xfe', b'\xfe\xff', b'\xff\xfe\x00\x00', b'\x00\x00\xfe\xff')):
                # 有 BOM，可能是文本，暂不按 NUL 判死刑，交给后面的解码/密度检查
                pass 
            else:
                return True
        
        # 2. 尝试严格 UTF-8 解码
        try:
            chunk.decode('utf-8')
            return False  # 成功解码，肯定是文本
        except UnicodeDecodeError:
            pass

        # 3. 解码失败，使用启发式兜底
        # 既然 UTF-8 解码失败了，如果它还是文本，那说明是其他编码 (如 GBK, Latin-1)。
        # 这里我们放宽阈值到 0.5，只要有一半像文本，就姑且认为是文本。
        return looks_binary_by_chars(chunk, threshold=0.5)

    except (IOError, PermissionError, OSError):
        # 读不到文件，保守视为二进制以免报错中断
        return True

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

def read_shebang(filepath: str) -> str:
    try:
        with open(filepath, 'rb') as f:
            first = f.readline(256)
        if first.startswith(b'#!'):
            return first.decode('utf-8', errors='ignore').strip().lower()
    except Exception:
        pass
    return ""

def generate_output_filename(base_name: str) -> str:
    if not os.path.exists(base_name):
        return base_name
    name, ext = os.path.splitext(base_name)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return f"{name}_{timestamp}{ext}"

def norm_ext(ext: str) -> str:
    ext = ext.strip()
    if not ext:
        return ext
    if not ext.startswith('.'):
        ext = '.' + ext
    return ext.lower()

def merge_type_groups(base: Dict[str, Dict[str, List[str]]],
                      override: Dict[str, Dict[str, List[str]]]) -> Dict[str, Dict[str, List[str]]]:
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
    将排除目录映射为“针对该 root 的绝对前缀集合”。
    优化：区分绝对路径和相对路径，避免不必要的 join。
    """
    out: Set[str] = set()
    for d in exclude_dirs:
        if os.path.isabs(d):
            p = d
        else:
            p = os.path.join(abs_root_dir, d)

        try:
            # 统一添加 abspath 和 realpath 两种形式
            # 确保以 os.sep 结尾，用于 startswith 前缀匹配
            abs_p = os.path.abspath(p)
            out.add(abs_p.rstrip(os.sep) + os.sep)
            
            real_p = os.path.realpath(abs_p)
            out.add(real_p.rstrip(os.sep) + os.sep)
        except Exception:
            continue
    return out

# ----------------- 核心逻辑：处理并写入单个文件 -----------------
def process_and_write_file(
    file_path: str,
    display_path: str,
    outfile,
    effective_exclude_exts: Set[str],
    active_filter: Optional[Dict[str, Set[str]]],
    type_groups: Dict[str, Dict[str, List[str]]],
    max_bytes: int,
    include_all_text: bool,
    quiet: bool,
    is_explicit_file: bool = False
) -> bool:
    """
    处理单个文件：检查排除规则、二进制、类型匹配，然后写入。
    返回 True 表示成功写入，False 表示被跳过。
    """
    # 1. 基础检查
    if not is_explicit_file:
        if not is_regular_file(file_path) or is_symlink(file_path):
            return False
    else:
        # 显式模式下，如果不存在，直接返回
        if not os.path.exists(file_path):
             if not quiet:
                 print(f"  ❌ 跳过：文件不存在 {file_path}")
             return False
        # 显式模式下，如果是目录，返回 False (应由主循环处理)
        if os.path.isdir(file_path):
            return False

    # 2. 后缀排除
    lname = os.path.basename(file_path).lower()
    if any(lname.endswith(ext) for ext in effective_exclude_exts):
        if is_explicit_file and not quiet:
            print(f"  ⚠️  警告：文件 {display_path} 匹配排除后缀，已跳过。")
        return False

    # 3. 二进制判定 (使用统一优化后的逻辑)
    if is_binary(file_path):
        if is_explicit_file and not quiet:
             print(f"  ⚠️  警告：文件 {display_path} 判定为二进制，已跳过。")
        return False

    # 4. 类型过滤
    if not include_all_text:
        if not file_matches_types(file_path, display_path, active_filter):
            return False

    # 5. 准备元数据
    if include_all_text:
        matched_str = "all-text"
    else:
        matched_groups = detect_matched_groups(file_path, display_path, type_groups)
        matched_str = ", ".join(matched_groups) if matched_groups else "unknown"

    # 6. 写入内容
    try:
        outfile.write(f"--- 文件路径: {display_path}\n")
        outfile.write(f"--- 文件类型: {matched_str}\n")
        outfile.write(f"--- 文件开始 ---\n\n")

        truncated = False
        if max_bytes and max_bytes > 0:
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
        
        if not quiet:
            print(f"  ✅ 已添加: {display_path}  ({matched_str})")
        return True

    except Exception as e:
        if not quiet:
            print(f"  ❌ 错误：无法读取文件 {file_path}: {e}")
        return False


# ----------------- 主收集逻辑 -----------------
def collect_files_to_single_file(
    paths: List[str],
    output_filename: str,
    extra_exclude_dirs: List[str],
    selected_types: List[str],
    type_groups: Dict[str, Dict[str, List[str]]],
    max_bytes: int,
    max_files: int,
    unsafe: bool,
    quiet: bool
) -> None:
    """遍历路径列表（目录递归/文件直接），合并内容。"""
    include_all_text = not selected_types
    active_filter = build_active_filters(type_groups, selected_types) if selected_types else None

    # 合并排除目录
    normalized_extra_excludes = {os.path.normpath(d.rstrip('/')) for d in extra_exclude_dirs}
    name_based_excludes = EXCLUDE_DIRS.union(normalized_extra_excludes)

    safe_output_filename = generate_output_filename(output_filename)
    safe_output_abs = os.path.abspath(safe_output_filename)

    effective_exclude_exts = set(EXCLUDE_EXTS)
    if not unsafe:
        effective_exclude_exts |= SENSITIVE_EXTS

    file_count = 0

    try:
        with open(safe_output_filename, 'w', encoding='utf-8', errors='ignore') as outfile:
            
            for input_path in paths:
                abs_input_path = os.path.abspath(input_path)
                
                # ----------- 情况 A: 输入是文件 -----------
                if os.path.isfile(abs_input_path):
                    # 检查是否是输出文件本身
                    if abs_input_path == safe_output_abs:
                        continue
                    
                    # 限流
                    if max_files and file_count >= max_files:
                        if not quiet: print(f"⏹️ 达到 --max-files 限制（{max_files}），停止。")
                        return

                    # 对于显式指定的文件，Display Path 使用相对当前目录的路径
                    display_path = os.path.relpath(abs_input_path, os.getcwd())
                    
                    success = process_and_write_file(
                        file_path=abs_input_path,
                        display_path=display_path,
                        outfile=outfile,
                        effective_exclude_exts=effective_exclude_exts,
                        active_filter=active_filter,
                        type_groups=type_groups,
                        max_bytes=max_bytes,
                        include_all_text=include_all_text,
                        quiet=quiet,
                        is_explicit_file=True
                    )
                    if success:
                        file_count += 1
                    continue

                # ----------- 情况 B: 输入是目录 -----------
                if not os.path.isdir(abs_input_path):
                    if not quiet:
                        print(f"⚠️  跳过：路径 '{input_path}' 不存在或不是目录/文件。")
                    continue

                # 目录处理逻辑
                root_dir = input_path # 保持原始输入以便做 relpath
                real_root = os.path.realpath(abs_input_path)
                abs_exclude_prefixes = _build_abs_excludes_for_root(abs_input_path, name_based_excludes)

                if not quiet:
                    print(f"\n📁 开始扫描目录: {abs_input_path}")

                for dirpath, dirnames, filenames in os.walk(abs_input_path, topdown=True, followlinks=False):
                    # 目录剪枝
                    kept_dirnames = []
                    for d in dirnames:
                        full = os.path.join(dirpath, d)
                        if d in name_based_excludes: continue
                        
                        abs_full = os.path.abspath(full)
                        real_full = os.path.realpath(abs_full)
                        if any(abs_full.startswith(p) or real_full.startswith(p) for p in abs_exclude_prefixes):
                            continue
                        if is_symlink(full): continue
                        kept_dirnames.append(d)
                    dirnames[:] = kept_dirnames

                    for filename in filenames:
                        if max_files and file_count >= max_files:
                            if not quiet: print(f"⏹️ 达到 --max-files 限制（{max_files}），停止。")
                            return

                        file_path = os.path.join(dirpath, filename)
                        
                        # 跳过输出文件自身
                        try:
                            if os.path.samefile(file_path, safe_output_abs): continue
                        except Exception: pass

                        # 防目录逃逸：真实路径必须仍在扫描根内
                        real_file = os.path.realpath(file_path)
                        if not (real_file == real_root or real_file.startswith(real_root + os.sep)):
                            continue

                        # 计算相对头路径
                        relative_path = os.path.relpath(file_path, abs_input_path)
                        header_path = sanitize_for_header(os.path.join(root_dir, relative_path).replace(os.sep, '/'))

                        success = process_and_write_file(
                            file_path=file_path,
                            display_path=header_path,
                            outfile=outfile,
                            effective_exclude_exts=effective_exclude_exts,
                            active_filter=active_filter,
                            type_groups=type_groups,
                            max_bytes=max_bytes,
                            include_all_text=include_all_text,
                            quiet=quiet,
                            is_explicit_file=False
                        )
                        if success:
                            file_count += 1

    except IOError as e:
        print(f"致命错误：无法写入到输出文件 {safe_output_filename}: {e}", file=sys.stderr)
        sys.exit(1)

    if not quiet:
        print("\n" + "="*60)
        print(f"🎉 处理完成！共 {file_count} 个文件被写入到 '{safe_output_filename}' 中。")
        print("="*60)

# ----------------- 配置加载/展示 -----------------
def load_types_config(path: str) -> Dict[str, Dict[str, List[str]]]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict): raise ValueError("类型配置必须是 JSON 对象")
        normed = {}
        for k, v in cfg.items():
            if not isinstance(v, dict): continue
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
        description="将源码/配置文件合并为一个文本文件。\n支持模式：\n1. 目录扫描：python collect.py dir1 dir2\n2. 指定文件：python collect.py file1.py file2.cpp\n3. 混合模式：python collect.py src/ main.py",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("paths", nargs="*", default=["."],
                        help="要收集的路径（目录或文件），默认为当前目录")
    parser.add_argument("--output", "-o", default="output.txt",
                        help="输出文件名（默认：output.txt）")
    parser.add_argument("--exclude-dirs", "-e", nargs="+", default=[], metavar="DIR",
                        help="额外排除的目录名或路径（仅对目录扫描有效）")
    parser.add_argument("--types", "-t", nargs="+", default=[],
                        help="指定收集的文件类型（如：yocto scripts python）")
    parser.add_argument("--list-types", action="store_true",
                        help="列出可用类型并退出")
    parser.add_argument("--types-config", default="",
                        help="JSON 文件路径，用于自定义类型映射")
    parser.add_argument("--max-bytes", type=int, default=8*1024*1024,
                        help="单文件最大读取字节数（默认 8 MiB）")
    parser.add_argument("--max-files", type=int, default=0,
                        help="最多采集的文件数（默认 0=不限制）")
    parser.add_argument("--unsafe", action="store_true",
                        help="关闭敏感后缀屏蔽")
    parser.add_argument("--quiet", action="store_true",
                        help="静默模式")

    args = parser.parse_args()
    args.exclude_dirs = [os.path.normpath(p) for p in args.exclude_dirs]

    groups = load_types_config(args.types_config) if args.types_config else FILE_TYPE_GROUPS

    if args.list_types:
        list_types(groups)
        sys.exit(0)

    unknown = [t for t in args.types if t and t not in groups]
    if unknown:
        print(f"⚠️  未知类型：{', '.join(unknown)}。可用类型见 --list-types。将忽略未知类型。")
        args.types = [t for t in args.types if t in groups]

    collect_files_to_single_file(
        args.paths,
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