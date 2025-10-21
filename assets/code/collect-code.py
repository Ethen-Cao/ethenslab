#!/usr/bin/python3
import os
import sys
import time
import argparse
from typing import Set, List

# --- 配置默认排除规则 ---
EXCLUDE_DIRS: Set[str] = {
    '.git', '__pycache__', 'node_modules','build',
    'dist', 'target', '.vscode', '.idea', 'venv', '.env'
}

EXCLUDE_EXTS: Set[str] = {
    # 编译产物
    '.pyc', '.pyo', '.o', '.so', '.a', '.dll', '.exe', '.class', '.jar',
    # 图片
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.ico', '.svg',
    # 音视频
    '.mp3', '.wav', '.mp4', '.mov', '.avi',
    # 压缩文件
    '.zip', '.tar', '.gz', '.rar', '.7z',
    # 文档和字体
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.eot', '.ttf', '.woff', '.woff2',
    # 数据库文件
    '.db', '.sqlite3'
}


# --- 辅助函数 ---

def is_binary(filepath: str, chunk_size: int = 1024) -> bool:
    """判断文件是否为二进制文件。"""
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(chunk_size)
            if b'\x00' in chunk:
                # 豁免 UTF-16/UTF-32 BOM
                if chunk.startswith((b'\xff\xfe', b'\xfe\xff', b'\xff\xfe\x00\x00', b'\x00\x00\xfe\xff')):
                    return False
                return True
    except (IOError, PermissionError):
        return True
    return False


def generate_output_filename(base_name: str) -> str:
    """如果输出文件已存在，则生成带时间戳的新文件名。"""
    if not os.path.exists(base_name):
        return base_name
    name, ext = os.path.splitext(base_name)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return f"{name}_{timestamp}{ext}"


def collect_files_to_single_file(
    root_dirs: List[str],
    output_filename: str,
    extra_exclude_dirs: List[str]
) -> None:
    """遍历一个或多个目录，将所有非二进制、非排除的文件内容合并到单个输出文件中。"""

    # 1️⃣ 合并默认和用户排除目录，并统一标准化为绝对路径
    normalized_extra_excludes = set(os.path.normpath(d.rstrip('/')) for d in extra_exclude_dirs)
    current_exclude_dirs = EXCLUDE_DIRS.union(normalized_extra_excludes)
    abs_exclude_paths = {os.path.abspath(d) for d in current_exclude_dirs if os.path.exists(d)}

    file_count = 0
    safe_output_filename = generate_output_filename(output_filename)

    try:
        with open(safe_output_filename, 'w', encoding='utf-8', errors='ignore') as outfile:
            for root_dir in root_dirs:
                abs_root_dir = os.path.abspath(root_dir)
                if not os.path.isdir(abs_root_dir):
                    print(f"⚠️  跳过：目录 '{root_dir}' 不存在。")
                    continue

                print(f"\n📁 开始处理目录: {abs_root_dir}")

                for dirpath, dirnames, filenames in os.walk(abs_root_dir, topdown=True):
                    # 2️⃣ 同时支持按目录名或绝对路径排除
                    dirnames[:] = [
                        d for d in dirnames
                        if d not in current_exclude_dirs
                        and os.path.abspath(os.path.join(dirpath, d)) not in abs_exclude_paths
                        and not any(os.path.abspath(os.path.join(dirpath, d)).startswith(p + os.sep)
                                    for p in abs_exclude_paths)
                    ]

                    for filename in filenames:
                        if any(filename.lower().endswith(ext) for ext in EXCLUDE_EXTS):
                            continue

                        file_path = os.path.join(dirpath, filename)
                        if is_binary(file_path):
                            print(f"  ⏩ 跳过二进制文件: {os.path.relpath(file_path, abs_root_dir)}")
                            continue

                        try:
                            relative_path = os.path.relpath(file_path, abs_root_dir)
                            # 使用相对项目根路径输出，避免泄露系统路径
                            header_path = os.path.join(root_dir, relative_path).replace(os.sep, '/')
                            outfile.write(f"--- 文件路径: {header_path} ---\n\n")

                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as infile:
                                for line in infile:
                                    outfile.write(line)

                            outfile.write("\n\n")
                            file_count += 1
                            print(f"  ✅ 已添加: {relative_path}")

                        except Exception as e:
                            print(f"  ❌ 错误：无法读取文件 {file_path}: {e}")

    except IOError as e:
        print(f"致命错误：无法写入到输出文件 {safe_output_filename}: {e}", file=sys.stderr)
        sys.exit(1)

    print("\n" + "="*60)
    print(f"🎉 处理完成！共 {file_count} 个文件被写入到 '{safe_output_filename}' 中。")
    print(f"ℹ️  本次排除的目录: {', '.join(sorted(list(current_exclude_dirs)))}")
    print("="*60)


# --- 主入口 ---
def main() -> None:
    parser = argparse.ArgumentParser(
        description="将一个或多个目录下的源代码合并为一个文本文件，用于AI代码分析。",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "directories",
        nargs="*",
        default=["."],
        help="要合并的一个或多个源代码目录路径。（默认：当前目录）"
    )
    parser.add_argument(
        "--output", "-o",
        default="combined_code.txt",
        help="指定输出文件名称。（默认：combined_code.txt）"
    )
    parser.add_argument(
        "--exclude-dirs", "-e",
        nargs="+",
        default=[],
        metavar="DIR",
        help="指定要排除的目录名或路径，可混合使用。（例如：-e logs temp ./hardware/.../include/）"
    )

    args = parser.parse_args()

    # 统一标准化路径
    args.exclude_dirs = [os.path.normpath(p) for p in args.exclude_dirs]

    collect_files_to_single_file(args.directories, args.output, args.exclude_dirs)


if __name__ == '__main__':
    main()
