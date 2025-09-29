import os
import zipfile
import tarfile
import gzip
import bz2
import shutil
import argparse

# rarfile 是可选依赖
try:
    import rarfile
    HAS_RAR = True
except ImportError:
    HAS_RAR = False


def extract_file(file_path, extract_to):
    """
    Extract a single compressed file based on its extension.
    Returns the path where the contents were extracted.
    """
    extracted_path = extract_to
    file_ext = os.path.splitext(file_path)[1].lower()
    file_base = os.path.basename(file_path)
    file_name_without_ext = os.path.splitext(file_base)[0]

    # 多文件压缩包：建子目录
    multi_file_exts = ['.zip', '.tar', '.tgz', '.tbz2', '.tar.gz', '.tar.bz2', '.rar']
    if file_ext in multi_file_exts:
        extracted_path = os.path.join(extract_to, file_name_without_ext)
        os.makedirs(extracted_path, exist_ok=True)

    try:
        if file_ext == '.zip':
            with zipfile.ZipFile(file_path, 'r') as zip_ref:
                zip_ref.extractall(extracted_path)

        elif file_ext in ['.tar', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2']:
            with tarfile.open(file_path) as tar_ref:
                tar_ref.extractall(extracted_path)

        elif file_ext == '.rar':
            if not HAS_RAR:
                print(f"rarfile module not installed. Please install it with:")
                print("    pip install rarfile")
                return None
            with rarfile.RarFile(file_path) as rar_ref:
                rar_ref.extractall(extracted_path)

        elif file_ext == '.gz':
            # 单文件压缩：解压到文件所在目录
            output_dir = os.path.dirname(file_path)
            output_path = os.path.join(output_dir, file_name_without_ext)
            if not os.path.exists(output_path):
                with gzip.open(file_path, 'rb') as f_in, open(output_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            extracted_path = output_dir

        elif file_ext == '.bz2':
            output_dir = os.path.dirname(file_path)
            output_path = os.path.join(output_dir, file_name_without_ext)
            if not os.path.exists(output_path):
                with bz2.open(file_path, 'rb') as f_in, open(output_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            extracted_path = output_dir

        else:
            print(f"Unsupported file format: {file_ext}")
            return None

    except Exception as e:
        print(f"Error extracting {file_path}: {e}")
        return None

    return extracted_path


def find_compressed_files(directory):
    """
    Find all compressed files in the directory (non-recursive).
    """
    compressed_extensions = [
        '.zip', '.tar', '.gz', '.bz2',
        '.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.rar'
    ]
    return [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f)) and
        os.path.splitext(f)[1].lower() in compressed_extensions
    ]


def extract_recursive(initial_file):
    """
    Recursively extract compressed files starting from the initial file.
    Extracts to the same directory as the initial file.
    """
    if not os.path.exists(initial_file):
        print(f"File not found: {initial_file}")
        return

    extract_to = os.path.dirname(os.path.abspath(initial_file))
    to_process = [os.path.abspath(initial_file)]
    processed_files = set()  # 避免死循环

    while to_process:
        current_file = to_process.pop(0)
        if current_file in processed_files:
            continue
        processed_files.add(current_file)

        print(f"Extracting: {current_file}")
        extracted_path = extract_file(current_file, extract_to)
        if extracted_path is None:
            continue

        # 查找新的压缩文件
        new_compressed = find_compressed_files(extracted_path)
        to_process.extend(new_compressed)


def main():
    parser = argparse.ArgumentParser(description="Recursively extract compressed files.")
    parser.add_argument("file_path", help="Path to the compressed file to extract")
    args = parser.parse_args()

    extract_recursive(args.file_path)


if __name__ == "__main__":
    main()
