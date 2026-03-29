# logcatv2 - DLT/JOUR 文本日志过滤工具

基于 `rg` + `awk` 的 DLT 文本过滤器，输入界面保持和 `logcat` 接近。

## 适用范围

当前仅支持两类文本日志：

- 常规 DLT 文本  
  例：`0 2026/03/26 18:38:59.087967 ... ECU1 ivcd ivcd ...`
- JOUR 文本  
  例：`0 2026/03/26 18:07:43.357536 ... ECU1 SYS- JOUR ... [2026/03/26 18:07:43.113299 openwfd_server[2204]: ...]`

## 语法

```bash
logcatv2 [options] [file/dir...]
```

不指定文件时默认搜索当前目录。

## 过滤逻辑

```text
Time AND (NOT Exclude) AND ( PID OR Source OR Keyword )
```

## 选项

| 选项 | 参数 | 说明 |
|------|------|------|
| `-f` | `<paths...>` | 指定搜索的文件或目录 |
| `-p` | `<pids...>` | 匹配 JOUR 内层 `proc[pid]` |
| `-s` | `<sources...>` | 匹配外层 `app/ctx`，以及 JOUR 内层 `proc` |
| `-k` | `<keywords...>` | 关键字包含过滤 |
| `-e` | `<keywords...>` | 关键字排除过滤 |
| `-t` | `<start> [end]` | 时间范围过滤 |
| `--plain` | | 纯文本输出 |

## 时间说明

- 当前时间匹配锚点是外层 DLT 时间
- 短格式：`HH:MM[:SS[.frac]]`
- 完整格式：`YYYY/MM/DD HH:MM:SS[.frac]`

例如：

```bash
logcatv2 -t "18:07:00" "18:08:00" dltlog/
logcatv2 -t "2026/03/26 18:07:00" "2026/03/26 18:08:00" dltlog/
```

## 示例

```bash
# 过滤 app/ctx
logcatv2 -s ivcd dltlog/dlt_115.txt

# 过滤 JOUR 内层进程名
logcatv2 -s openwfd_server dltlog/journal_155.txt

# 过滤 JOUR 内层 pid
logcatv2 -p 2204 dltlog/journal_155.txt

# 组合过滤
logcatv2 -s openwfd_server -e "pidfd closed" dltlog/journal_155.txt
```

## 边界

- `-p` 不匹配外层 DLT 数字字段
- 不支持二进制 `.dlt`
- 不支持 `.gz/.tgz`
- 不支持 `dmesg`
- 不支持 boot/UEFI 原始日志
