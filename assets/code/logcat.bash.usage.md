# logcat - Android Logcat 日志过滤工具

基于 `rg` + `awk` 的高性能 logcat 文件过滤器。

## 依赖

- [ripgrep](https://github.com/BurntSushi/ripgrep) (`rg`)
- `awk` (gawk / mawk 均可)

## 语法

```
logcat [options] [file/dir...]
```

不指定文件时默认搜索当前目录。

## 过滤逻辑

```
Time AND (NOT Exclude) AND ( PID OR Tag OR Keyword )
```

- **Time**: 时间范围门控，最先执行
- **Exclude**: 排除词，命中即丢弃
- **PID / Tag / Keyword**: 三者之间是 OR 关系，命中任一即通过
- 如果只指定了 Time 和/或 Exclude（没有 PID/Tag/Keyword），则所有未被排除的行都输出

## 选项

| 选项 | 参数 | 说明 |
|------|------|------|
| `-f` | `<paths...>` | 指定搜索的文件或目录（空格分隔多个） |
| `-p` | `<pids...>` | 按进程 PID 过滤（空格分隔多个，OR 关系） |
| `-s` | `<tags...>` | 按 Log Tag 过滤（空格分隔多个，OR 关系） |
| `-k` | `<keywords...>` | 按关键字包含过滤（空格分隔多个，OR 关系） |
| `-e` | `<keywords...>` | 排除包含指定关键字的行（空格分隔多个，OR 关系） |
| `-t` | `<start> [end]` | 按时间范围过滤，支持两种格式（见下文） |
| `--plain` | | 纯文本输出，不带文件名和行号 |

### 时间格式

`-t` 支持两种格式，不可混用：

| 格式 | 示例 | 说明 |
|------|------|------|
| 短格式（仅时间） | `-t "10:30:00" "10:35:00"` | 忽略日期，只按时间段过滤 |
| 完整格式（日期+时间） | `-t "03-24 10:30:00" "03-24 10:35:00"` | 精确到日期的范围过滤 |

省略 `end` 时表示从 `start` 到文件末尾。

## 示例

### 基本过滤

```bash
# 按 Tag 过滤
logcat -s WindowManager /path/to/logcat.log

# 按多个 Tag 过滤 (OR)
logcat -s WindowManager ActivityManager /path/to/logcat.log

# 按 PID 过滤
logcat -p 1462 /path/to/logcat.log

# 按关键字过滤
logcat -k "ANR" /path/to/logcat.log
```

### 时间范围

```bash
# 只看 10:50 到 10:51 之间的日志
logcat -t "10:50:00" "10:51:00" /path/to/logcat.log

# 精确到日期
logcat -t "03-24 10:50:00" "03-24 10:51:00" /path/to/logcat.log

# 从某个时间点开始到文件末尾
logcat -t "10:50:00" /path/to/logcat.log
```

### 排除噪音

```bash
# 过滤 Error 关键字，排除 chatty 和 Codec2 的干扰
logcat -k "Error" -e "chatty" "Codec2" /path/to/logcat.log
```

### 组合使用

```bash
# 看某个进程在某段时间内的 Error 日志，排除已知噪音
logcat -t "10:49:00" "10:50:00" -p 1462 -k "Error" -e "chatty" /path/to/logcat.log

# 多 Tag + 排除，纯文本输出（便于管道处理）
logcat -s WindowManager ActivityManager -e "Didn't find task" --plain /path/to/logcat.log | wc -l
```

### 搜索目录

```bash
# 搜索整个目录下所有日志文件
logcat -s "UpdateService" /path/to/log_dir/

# 指定多个文件/目录
logcat -f /tmp/log1.txt /tmp/log2.txt -k "crash"
```

## 输出格式

默认输出带颜色的文件名和行号：

```
/path/to/file.log:12345: 03-24 10:50:00.123  1462  1640 D WindowManager: Focus moving ...
^紫色文件名        ^绿色行号  ^原始日志行
```

使用 `--plain` 去掉文件名/行号前缀，只输出原始日志行。

## 注意事项

- `-k`、`-s`、`-e` 的值会作为 awk 正则表达式使用。如果要搜索含正则特殊字符的文本（如 `(`、`[`、`.`），需要转义：`-k "error\(1\)"`
- 仅处理标准 `threadtime` 格式的 logcat 行（`MM-DD HH:MM:SS.mmm PID TID LEVEL Tag: msg`），非标准行（如 `--------- switch to main`）会被跳过
- 二进制文件和压缩包会被 `rg` 自动跳过
