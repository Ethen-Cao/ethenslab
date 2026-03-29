# analyze_archive_logs.sh - 解压、转换、过滤统一入口

把以下流程串起来：

1. 安全解压压缩包
2. 递归定位 `.dlt`
3. 批量转成 `.txt`
4. 调用 `logcat` 或 `logcatv2` 过滤

## 语法

```bash
analyze_archive_logs.sh [wrapper-options] <input...> -- [filter-options]
analyze_archive_logs.sh [wrapper-options] <input...>
```

说明：

- `input` 放在 `--` 之前
- 过滤参数放在 `--` 之后
- `--` 后面的参数会原样传给 `logcat` 或 `logcatv2`

## Wrapper 选项

| 选项 | 说明 |
|------|------|
| `--tool auto` | 自动识别，优先 DLT/JOUR 文本，其次 Android |
| `--tool logcat` | 强制用 `logcat` |
| `--tool logcatv2` | 强制用 `logcatv2` |
| `--work-root <dir>` | 指定归档解压工作目录 |
| `--cleanup` | 自动删除脚本临时创建的工作目录 |

## 典型用法

```bash
# 直接分析目录中的 DLT/JOUR 文本
analyze_archive_logs.sh ./linux_log --tool logcatv2 -- --plain -s ivcd

# 分析压缩包，自动解压并转换 dlt
analyze_archive_logs.sh issue_logs.tgz --tool logcatv2 -- --plain -k "socket_fd error -1"

# 分析 Android 包
analyze_archive_logs.sh android_logs.zip --tool logcat -- --plain -t "03-26 18:07:00" "03-26 18:08:00" -s ActivityManager
```

## 当前行为

- 归档输入：调用 `/home/ethen/bin/safe_unzip_timestamped.py --keep`
- `.dlt` 转换：在包含 `.dlt` 的目录中调用 `/home/ethen/bin/dlt2txt.sh`
- `auto` 模式：
  - 先检测 DLT/JOUR 文本
  - 再检测 Android `threadtime`

## 边界

- `--` 后不要再传 `-f`，输入路径应放在脚本参数中
- 目录输入当前不会自动把目录中的嵌套归档重新解压到独立工作区
- `.dlt` 转换依赖 `dlt-convert`
