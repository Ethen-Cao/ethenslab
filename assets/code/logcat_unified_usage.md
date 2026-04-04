# `logcat_unified.sh`

## 功能概述

`logcat_unified.sh` 用于把多种日志源整理成一条统一的时间线，并在这条时间线上做过滤输出。

当前支持的输入类型：

- Android logcat 文本
  - 典型格式：`03-24 09:18:57.503591  776  801 I Tag: message`
- Linux / userspace ISO 风格日志
  - 典型格式：`2026-03-24 04:57:37.190 ...`
- 传统 syslog / kernel 日志
  - 典型格式：`Jan 01 13:04:54.139903 host kernel: message`
- 经过外部脚本转换后的 DLT 文本
  - 典型格式：`3 2026/03/24 12:54:48.049642  532652054 170 ECU1 rpcd rpcd ...`

脚本的目标不是简单拼接输出，而是：

1. 识别不同日志格式中的时间戳、PID、source/tag。
2. 规范化成可比较的统一时间键。
3. 对所有输入做全局时间排序。
4. 在统一时间线上做 PID、source、关键字、排除关键字和时间窗口过滤。

## 实现原理

脚本采用“两阶段流式处理”：

1. 文件发现阶段
   - 递归遍历指定文件或目录。
   - 普通文本日志进入 text 流。
   - 原始 `.dlt` 二进制文件直接跳过，不在脚本内解码。

2. 输入规范化阶段
   - 文本日志按原始文件名、行号、内容打包成统一记录。
   - 外部脚本转换后的 DLT 文本会作为普通文本输入参与后续解析。

3. 解析与归一化阶段
   - 在单个 `awk` 中识别不同格式。
    - 把时间统一规范成 `YYYY-MM-DDTHH:MM:SS.ffffff` 形式，作为全局排序键。
    - Android 和传统 syslog 这类缺少年份的日志，会优先从路径中的锚点日期推断年份，尽量避免跨年错序。
    - Android tag 支持带空格的场景，不再只截取单个字段。
   - DLT 转换文本中的 `YYYY/MM/DD HH:MM:SS.ffffff` 格式会被直接识别并纳入统一时间线。

4. 过滤与输出阶段
   - 先做时间过滤，再做排除关键字过滤。
   - 然后按 `PID OR Source OR Keyword` 逻辑做包含过滤。
   - 最终按全局时间键排序输出。

## 过滤逻辑

脚本使用下面的逻辑：

`Time AND (NOT Exclude) AND ( PID OR Source OR Keyword )`

说明：

- 如果没有传 `-p/-s/-k`，则默认不过滤包含条件。
- `-e` 永远是排除条件。
- `-i` 只影响 source 和关键字匹配，不影响时间比较。

## 命令行参数

```text
Usage: logcat_unified.sh [options] [file/dir...]

Options:
  -f <paths...>           Specify files/dirs to search
  -p <pid...>             Filter by PID regex; repeatable
  -s <source...>          Filter by source/tag regex; repeatable
  -k <keyword...>         Filter by keyword regex; repeatable
  -e <keyword...>         Exclude keyword regex; repeatable
  -i, --ignore-case       Ignore case for source/keyword matching
  -t <start> <end>        Time range: HH:MM[:SS[.frac]] or "YYYY-MM-DD HH:MM[:SS[.frac]]"
  --plain                 Output plain text (no file:line prefix)
  -h, --help              Show this help
  --                      End options; following args are treated as paths

Notes:
  - Raw .dlt files are skipped; convert them to text before running this script.
```

## 时间过滤说明

`-t` 支持两种时间模式：

- 时钟模式
  - `-t 04:57 05:10`
  - `-t 04:57:37.190 04:57:37.193`
- 完整日期时间模式
  - `-t "2026-03-24 04:57:37.190" "2026-03-24 04:57:37.193"`

规则：

- 起止时间必须属于同一种模式。
- 时钟模式只比较一天中的时分秒，适合在已知日期范围的日志中快速截窗。
- 当时钟模式的起点大于终点时，脚本按跨午夜窗口处理。

## 使用建议

### 1. 优先显式指定搜索范围

目录里的日志很多时，不要直接在大目录根上裸跑。优先使用 `-f` 或显式位置参数，把范围缩到你关心的文件或子目录。

```bash
logcat_unified.sh -f ./log_android/android/260401-14-27-49_271_20260324_094441.logcat.log
logcat_unified.sh -f ./log_linux/syslog/260401-14-27-54_407_20260324_045737
```

### 2. 先用关键字缩小，再加时间窗口

```bash
logcat_unified.sh --plain \
  -k 'DOIP_PROGRAM|voydoip|rpcd' \
  -t "2026-03-24 04:57:37" "2026-03-24 04:58:00" \
  -f ./log_android/android/... ./log_linux/syslog/... ./converted_dlt/dlt_637.txt
```

### 3. 用 `--plain` 方便继续管道处理

```bash
logcat_unified.sh --plain -k 'timeout|error' -f ./log_linux/syslog/... | less
```

### 4. 用默认彩色输出定位源文件和行号

```bash
logcat_unified.sh -k DOIP_PROGRAM -f ./log_android/android/260401-14-27-41_070_20260321_202051.logcat.log
```

输出会带上 `file:line` 前缀，方便回跳原始文件。

## 常见用法示例

### 按 source/tag 查 Android 和 syslog

```bash
logcat_unified.sh --plain -s 'kernel|qgptp_monitor|voydoip' \
  -f ./linux_nocamera_ok_1837.txt ./log_linux/syslog/260401-14-27-54_407_20260324_045737/407_20260324_045737.log
```

### 按 PID 查统一时间线

```bash
logcat_unified.sh --plain -p '5247|2061|1358' \
  -f ./log_android/android/... ./log_linux/syslog/...
```

### 在 DLT 转换文本中按应用名或关键字过滤

```bash
logcat_unified.sh --plain -s rpcd -f ./converted_dlt/dlt_637.txt
logcat_unified.sh --plain -k 'rpcd_mcu_spi|frame_id = 33824' -f ./converted_dlt/dlt_637.txt
```

### 用排除条件去掉噪声

```bash
logcat_unified.sh --plain \
  -k 'error|timeout|fail' \
  -e 'pidfd closed successfully|GCP is not supported' \
  -f ./log_android/android/... ./log_linux/syslog/...
```

### 使用位置参数而不是 `-f`

```bash
logcat_unified.sh --plain -k DOIP_PROGRAM -- \
  ./log_android/android/260401-14-27-41_070_20260321_202051.logcat.log/070_20260321_202051.logcat.log
```

`--` 可以避免位置路径被误判为前面选项的取值。

## 依赖

- `bash`
- `awk`
- `find`
- `sort`
- `xargs`

说明：

- 脚本本身不负责解码原始 `.dlt`。
- 原始 `.dlt` 文件会被跳过，并输出 warning。
- 需要先由外部脚本把 DLT 转成文本，再把转换结果交给 `logcat_unified.sh`。

## 已知边界

### 1. 超大目录仍然建议缩小输入范围

脚本已经是流式处理，不会先把所有日志读进内存再排序；但如果你把非常大的目录整体扔进去，I/O 和排序成本依然会高。

### 2. 年份推断依赖路径锚点

对于只有 `MM-DD` 或 `Mon DD` 的日志，脚本会尽量从路径中的日期锚点推断年份。这比简单使用当前年份可靠，但极端的跨年归档布局仍可能需要人工确认。

### 3. 过滤条件是正则

`-p/-s/-k/-e` 传入的是正则表达式，而不是字面量字符串。如果关键字里包含正则特殊字符，需要自行转义。

## 推荐部署方式

建议把脚本源码保存在工作区：

`~/workspace/github/ethenslab/assets/code/logcat_unified.sh`

然后在 `~/bin/` 下放一个软链接：

`~/bin/logcat_unified.sh -> ~/workspace/github/ethenslab/assets/code/logcat_unified.sh`

这样后续维护、提交和本地调用都在同一个来源上。
