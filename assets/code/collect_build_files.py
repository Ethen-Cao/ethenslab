import os

# 需要搜索的编译文件名关键字，可以按需扩展
BUILD_FILES = [
    "Makefile",
    "CMakeLists.txt",
    "build.sh",
    "configure",
    ".pro",
    ".pri",
    ".mk",
    ".bp",
]

def is_build_file(filename):
    return any(filename == f or filename.endswith(f) for f in BUILD_FILES)

def main(root_dir):
    output_file = os.path.join(root_dir, "build_files.txt")

    with open(output_file, "w", encoding="utf-8") as out:
        for dirpath, dirnames, filenames in os.walk(root_dir):
            rel_dir = os.path.relpath(dirpath, root_dir)
            for fname in filenames:
                if is_build_file(fname):
                    rel_path = os.path.normpath(os.path.join(rel_dir, fname))
                    if rel_path == ".":
                        rel_path = fname
                    out.write(f"{rel_path}\n")
                    out.write("=" * len(rel_path) + "\n")
                    try:
                        with open(os.path.join(dirpath, fname), "r", encoding="utf-8", errors="ignore") as f:
                            out.write(f.read())
                    except Exception as e:
                        out.write(f"<<无法读取文件: {e}>>\n")
                    out.write("\n\n")

    print(f"编译文件信息已写入 {output_file}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法: python collect_build_files.py <代码根目录>")
    else:
        main(sys.argv[1])
