#!/usr/bin/env python3
"""
safe_unzip_timestamped.py - 安全递归解压工具
修改记录：
 - 输出目录格式改为: YYMMDD-HH-MM-SS_原目录名
 - 默认删除源文件 (使用 --keep 保留)
"""
import os
import sys
import shutil
import logging
import argparse
import zipfile
import tarfile
import tempfile
import gzip
import datetime  # [新增] 用于生成时间戳
from pathlib import Path, PurePosixPath
from typing import Optional

# optional deps
try:
    import py7zr
except ImportError:
    py7zr = None

try:
    import rarfile
except ImportError:
    rarfile = None

logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(levelname)s] - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger(__name__)

# recognized archive suffixes (lowercase)
ARCHIVE_SUFFIXES = ('.zip', '.tar', '.tar.gz', '.tgz', '.tar.xz', '.txz', '.tar.bz2', '.tbz', '.gz', '.7z', '.rar')

def is_archive_path(p: Path) -> bool:
    name = p.name.lower()
    return any(name.endswith(s) for s in ARCHIVE_SUFFIXES)

def safe_member_name(member_name: str) -> bool:
    """
    检查归档成员名是否安全（无绝对路径、无上级引用、无 Windows 盘符等）
    """
    if not member_name:
        return False
    pp = PurePosixPath(member_name)
    if pp.is_absolute():
        return False
    parts = pp.parts
    if '..' in parts:
        return False
    if len(member_name) >= 2 and member_name[1] == ':' and member_name[0].isalpha():
        return False
    if '\\' in member_name:
        return False
    return True

class SecureUnzipper:
    def __init__(self, keep_orig: bool = False, dry_run: bool = False):
        self.keep_orig = keep_orig
        self.dry_run = dry_run
        self.processed_inodes = set()

    def get_file_id(self, path: Path):
        try:
            st = path.resolve().stat()
            return (st.st_dev, st.st_ino)
        except Exception:
            return None

    def get_output_folder_name(self, filename: str) -> str:
        """
        [修改] 生成输出目录名：YYMMDD-HH-MM-SS_原名称
        """
        lower = filename.lower()
        base_name = filename + "_extracted" # default fallback

        # 1. 确定基础名称 (去掉后缀)
        found_suffix = False
        for suf in ('.tar.gz', '.tar.xz', '.tar.bz2', '.tar', '.tgz', '.txz', '.tbz'):
            if lower.endswith(suf):
                base_name = filename[: -len(suf)]
                found_suffix = True
                break
        
        if not found_suffix:
            if '.' in filename:
                base_name = filename.rsplit('.', 1)[0]
            else:
                base_name = filename

        # 2. [新增] 添加时间戳前缀 (YYMMDD-HH-MM-SS)
        timestamp = datetime.datetime.now().strftime("%y%m%d-%H-%M-%S")
        return f"{timestamp}_{base_name}"

    def ensure_parent(self, p: Path):
        p.parent.mkdir(parents=True, exist_ok=True)

    def safe_move_contents(self, src_root: Path, dst_root: Path):
        """
        将 src_root 下的普通文件移动到 dst_root，跳过 symlink/特殊文件
        """
        logger.debug(f"safe_move_contents: {src_root} -> {dst_root}")
        dst_root = dst_root.resolve()
        src_root = src_root.resolve()

        for root, dirs, files in os.walk(src_root):
            root_path = Path(root)
            rel = root_path.relative_to(src_root)
            target_dir = dst_root / rel
            if not self.dry_run:
                target_dir.mkdir(parents=True, exist_ok=True)

            for name in files:
                src_file = root_path / name
                dst_file = target_dir / name
                try:
                    if src_file.is_symlink():
                        logger.warning(f"Skipping symlink: {src_file}")
                        continue
                    if not src_file.is_file():
                        logger.warning(f"Skipping non-regular file: {src_file}")
                        continue

                    if not str(dst_file.resolve()).startswith(str(dst_root)):
                        logger.error(f"Target path outside destination: {dst_file} (skip)")
                        continue

                    if self.dry_run:
                        logger.info(f"[DRY-RUN] Move {src_file} -> {dst_file}")
                    else:
                        if dst_file.exists():
                            logger.info(f"Overwriting existing: {dst_file}")
                            dst_file.unlink()
                        shutil.move(str(src_file), str(dst_file))
                except Exception as e:
                    logger.error(f"Failed moving {src_file} -> {dst_file}: {e}")

    # ------------ extraction helpers ------------
    def extract_zip_safe(self, archive_path: Path, temp_dir: Path) -> bool:
        try:
            with zipfile.ZipFile(archive_path, 'r') as zf:
                names = zf.namelist()
                for member in names:
                    if not safe_member_name(member):
                        logger.error(f"Unsafe member in zip: {member}")
                        return False
                for member in names:
                    info = zf.getinfo(member)
                    if member.endswith('/'):
                        (temp_dir / member).mkdir(parents=True, exist_ok=True)
                        continue
                    target = temp_dir / member
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info, 'r') as src_f, open(target, 'wb') as dst_f:
                        shutil.copyfileobj(src_f, dst_f)
                    try:
                        perm = (info.external_attr >> 16) & 0o777
                        if perm:
                            os.chmod(target, perm)
                    except Exception:
                        pass
            return True
        except Exception as e:
            logger.error(f"extract_zip_safe error: {e}")
            return False

    def extract_tar_safe(self, archive_path: Path, temp_dir: Path) -> bool:
        try:
            with tarfile.open(archive_path, 'r:*') as tf:
                members = tf.getmembers()
                for m in members:
                    if not safe_member_name(m.name):
                        logger.error(f"Unsafe member in tar: {m.name}")
                        return False
                for m in members:
                    target = temp_dir / m.name
                    if m.isdir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    if m.issym() or m.islnk() or m.isdev() or m.isfifo():
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    f = tf.extractfile(m)
                    if f:
                        with open(target, 'wb') as out_f:
                            shutil.copyfileobj(f, out_f)
                        try:
                            os.chmod(target, m.mode)
                        except Exception:
                            pass
                return True
        except Exception as e:
            logger.error(f"extract_tar_safe error: {e}")
            return False

    def extract_gzip_single(self, archive_path: Path, temp_dir: Path) -> bool:
        try:
            name = archive_path.name
            if name.lower().endswith('.gz'):
                base = name[:-3]
            else:
                base = name + '.out'
            out_path = temp_dir / base
            with gzip.open(archive_path, 'rb') as src_f, open(out_path, 'wb') as out_f:
                shutil.copyfileobj(src_f, out_f)
            return True
        except Exception as e:
            logger.error(f"extract_gzip_single error: {e}")
            return False

    def extract_7z_safe(self, archive_path: Path, temp_dir: Path) -> bool:
        if not py7zr:
            logger.error("py7zr not installed.")
            return False
        try:
            with py7zr.SevenZipFile(archive_path, mode='r') as z:
                names = z.getnames()
                for n in names:
                    if not safe_member_name(n):
                        logger.error(f"Unsafe member in 7z: {n}")
                        return False
                z.extractall(path=str(temp_dir))
            return True
        except Exception as e:
            logger.error(f"extract_7z_safe error: {e}")
            return False

    def extract_rar_safe(self, archive_path: Path, temp_dir: Path) -> bool:
        if not rarfile:
            logger.error("rarfile not installed.")
            return False
        try:
            with rarfile.RarFile(archive_path) as rf:
                names = rf.namelist()
                for n in names:
                    if not safe_member_name(n):
                        logger.error(f"Unsafe member in rar: {n}")
                        return False
                rf.extractall(path=str(temp_dir))
            return True
        except Exception as e:
            logger.error(f"extract_rar_safe error: {e}")
            return False

    def extract_archive(self, archive_path: Path, output_dir: Path) -> bool:
        name = archive_path.name.lower()
        with tempfile.TemporaryDirectory(prefix="safe_unzip_") as tmpd:
            temp_dir = Path(tmpd)
            extracted = False
            
            if name.endswith('.zip'):
                extracted = self.extract_zip_safe(archive_path, temp_dir)
            elif name.endswith(('.tar', '.tar.gz', '.tgz', '.tar.xz', '.txz', '.tar.bz2', '.tbz')):
                extracted = self.extract_tar_safe(archive_path, temp_dir)
            elif name.endswith('.gz') and not name.endswith('.tar.gz'):
                extracted = self.extract_gzip_single(archive_path, temp_dir)
            elif name.endswith('.7z'):
                extracted = self.extract_7z_safe(archive_path, temp_dir)
            elif name.endswith('.rar'):
                extracted = self.extract_rar_safe(archive_path, temp_dir)
            else:
                return False

            if not extracted:
                return False

            if self.dry_run:
                logger.info(f"[DRY-RUN] Would move contents to {output_dir}")
                return True

            try:
                self.safe_move_contents(temp_dir, output_dir)
                return True
            except Exception as e:
                logger.error(f"Failed to move sanitized contents: {e}")
                return False

    # ------------ recursion ------------
    def process_recursive(self, target: Path, output_base: Optional[Path] = None):
        try:
            target = target.resolve()
        except Exception as e:
            logger.error(f"Cannot resolve path {target}: {e}")
            return

        if target.is_dir():
            try:
                children = list(target.iterdir())
            except Exception as e:
                logger.error(f"Cannot list directory {target}: {e}")
                return
            for child in children:
                self.process_recursive(child, output_base=None)
            return

        if not is_archive_path(target):
            return

        fid = self.get_file_id(target)
        if fid and fid in self.processed_inodes:
            return

        folder = self.get_output_folder_name(target.name)
        if output_base:
            final_out = output_base / folder
        else:
            final_out = target.parent / folder

        if final_out.exists():
            logger.warning(f"Output folder exists, skip: {final_out}")
            return

        logger.info(f"Extracting {target} -> {final_out}")
        success = self.extract_archive(target, final_out)

        if success:
            # 默认删除源文件
            if not self.keep_orig:
                try:
                    target.unlink()
                    logger.info(f"Removed original archive: {target}")
                except Exception as e:
                    logger.warning(f"Could not remove original {target}: {e}")

            if fid:
                self.processed_inodes.add(fid)

            self.process_recursive(final_out, output_base=None)
        else:
            if final_out.exists():
                try:
                    if not any(final_out.iterdir()):
                        final_out.rmdir()
                except Exception:
                    pass

def main():
    parser = argparse.ArgumentParser(description="安全递归解压工具")
    parser.add_argument('inputs', nargs='+', help='输入文件或目录')
    parser.add_argument('-o', '--output', help='顶层输出目录')
    parser.add_argument('--keep', action='store_true', help='保留原始压缩包 (默认删除)')
    parser.add_argument('--dry-run', action='store_true', help='只打印操作')
    args = parser.parse_args()

    unzipper = SecureUnzipper(keep_orig=args.keep, dry_run=args.dry_run)

    if py7zr is None:
        logger.info("py7zr not installed: .7z will be skipped")
    if rarfile is None:
        logger.info("rarfile not installed: .rar will be skipped")

    global_out = None
    if args.output:
        global_out = Path(args.output).resolve()
        if not global_out.exists() and not args.dry_run:
            global_out.mkdir(parents=True, exist_ok=True)

    for inp in args.inputs:
        p = Path(inp)
        if not p.exists():
            logger.error(f"Input not found: {p}")
            continue
        if p.is_file():
            out_base = global_out if global_out else p.parent
            unzipper.process_recursive(p, output_base=out_base)
        else:
            unzipper.process_recursive(p, output_base=None)

    logger.info("Done.")

if __name__ == '__main__':
    main()