# super_image_diff.py 使用说明

## 1. 脚本用途

`super_image_diff.py` 用于对比两个 Android `super.img`，自动完成以下分析：

- 比较 `super.img` 稀疏文件大小变化
- 比较 `super` 动态分区布局和 `used_size` 变化
- 解包动态分区并统计各分区大小变化
- 统计 `apk`、`so`、`apex`、`model_data`、`media` 等文件类型的占比变化
- 输出 Top 目录变化和 Top 文件变化
- 生成 `md`、`csv`、`json` 报告


## 2. 环境依赖

### 2.1 Python 依赖

需要：

- `python3`

脚本只使用 Python 标准库，不需要额外执行 `pip install`。


### 2.2 外部命令依赖

脚本运行时需要以下命令：

- `simg2img`
- `lpdump`
- `lpunpack`
- `debugfs`
- `dumpe2fs`
- `file`

说明：

- 不依赖 `7z`
- 不依赖 `mount`
- 不依赖 root 权限


### 2.3 `file` 命令注意事项

如果 `file` 不是系统自带，而是跟脚本一起打包分发，通常还需要一起提供：

- `magic.mgc`

否则 `file` 可能无法正确识别镜像类型。


## 3. 工具查找顺序

脚本查找工具的顺序如下：

1. 先读取环境变量指定的路径
2. 再从当前系统 `PATH` 中查找
3. 最后尝试脚本中预置的若干候选路径

可用的环境变量如下：

- `SIMG2IMG`
- `LPDUMP`
- `LPUNPACK`
- `DEBUGFS`
- `DUMPE2FS`
- `FILE`


## 4. 推荐目录结构

如果你想把脚本和工具一起放在同一个目录中，推荐结构如下：

```text
super_image_diff.py
super_image_diff.md
simg2img
lpdump
lpunpack
debugfs
dumpe2fs
file
magic.mgc
```

说明：

- `python3` 通常直接使用目标服务器系统自带版本
- 如果 `file` 是自带二进制，建议同时带上 `magic.mgc`


## 5. 如何运行

### 5.1 最简单的运行方式

```bash
python3 ./super_image_diff.py OLD_SUPER.img NEW_SUPER.img
```

例如：

```bash
python3 ./super_image_diff.py \
  ./H47A-cdc-8397-H47A_PPC0_RC16_5_20260129-soc_full-userdebug-16.5.215-20260327161938/la_au.vendor.16.0.2/LINUX/android/out/target/product/himalayas/super.img \
  ./H47A-cdc-8397-dev_REL1_CSP1_20260219-soc_full-userdebug-16.6.7.221-20260410222941/la_au.vendor.16.0.2/LINUX/android/out/target/product/himalayas/super.img
```


### 5.2 指定输出工作目录

默认输出目录为：

```text
analysis_short_term
```

也可以通过 `--workdir` 指定：

```bash
python3 ./super_image_diff.py OLD_SUPER.img NEW_SUPER.img --workdir ./my_super_diff
```


### 5.3 指定输出 Top 条目数量

默认输出 Top 30 项，可以通过 `--top` 调整：

```bash
python3 ./super_image_diff.py OLD_SUPER.img NEW_SUPER.img --top 50
```


### 5.4 扫描全部动态分区

默认情况下，脚本优先扫描有变化的逻辑分区。

如果希望无论分区大小是否变化，都强制扫描全部逻辑分区，可使用：

```bash
python3 ./super_image_diff.py OLD_SUPER.img NEW_SUPER.img --all-partitions
```


### 5.5 使用环境变量指定工具路径

当工具不在系统 `PATH` 中时，建议显式指定：

```bash
SIMG2IMG=/path/to/simg2img \
LPDUMP=/path/to/lpdump \
LPUNPACK=/path/to/lpunpack \
DEBUGFS=/path/to/debugfs \
DUMPE2FS=/path/to/dumpe2fs \
FILE=/path/to/file \
python3 ./super_image_diff.py OLD_SUPER.img NEW_SUPER.img
```


### 5.6 工具与脚本在同一目录时的运行方式

如果工具和脚本都放在同一个目录下，可以这样运行：

```bash
DIR=$(cd "$(dirname "$0")" && pwd)
export PATH="$DIR:$PATH"
export MAGIC="$DIR/magic.mgc"
python3 "$DIR/super_image_diff.py" OLD_SUPER.img NEW_SUPER.img
```

或者直接显式指定工具路径：

```bash
DIR=$(pwd)
SIMG2IMG="$DIR/simg2img" \
LPDUMP="$DIR/lpdump" \
LPUNPACK="$DIR/lpunpack" \
DEBUGFS="$DIR/debugfs" \
DUMPE2FS="$DIR/dumpe2fs" \
FILE="$DIR/file" \
python3 "$DIR/super_image_diff.py" OLD_SUPER.img NEW_SUPER.img
```


## 6. 输出内容说明

假设使用默认工作目录 `analysis_short_term`，脚本会生成如下内容：

```text
analysis_short_term/
  raw/
  layout/
  unpacked/
  fs/
  reports/
```

各目录说明：

- `raw/`
  保存 sparse `super.img` 转换后的 raw 镜像
- `layout/`
  保存 `lpdump -j` 导出的动态分区布局 JSON
- `unpacked/`
  保存 `lpunpack` 导出的逻辑分区镜像
- `fs/`
  保存通过 `debugfs` 解出的分区文件树
- `reports/`
  保存最终报告


### 6.1 主要报告文件

- `reports/summary.md`
  汇总报告，适合直接阅读
- `reports/summary.json`
  结构化结果，适合后续程序消费
- `reports/partition_diff.csv`
  分区大小变化表
- `reports/category_diff.csv`
  文件类型占比变化表
- `reports/bucket_diff.csv`
  目录维度变化表
- `reports/file_diff_top.csv`
  Top 文件变化表


## 7. 控制台输出说明

脚本执行完成后会在控制台打印摘要，例如：

- 旧版本和新版本 `super.img` 文件大小
- `Sparse file delta`
- `used_size delta`
- Top 分区变化
- Top 文件类型变化
- 报告输出目录

其中：

- `Sparse file delta`
  表示两个 sparse `super.img` 文件本身的大小差值
- `used_size delta`
  表示 `super` 内部逻辑分区实际使用空间的差值


## 8. 常见问题

### 8.1 为什么脚本运行很慢

原因通常有两类：

- `super.img` 很大，`simg2img` 和 `lpunpack` 本身耗时较长
- 脚本会用 `debugfs` 抽取分区文件树用于文件级归因

这是预期行为，尤其是 `system.img` 很大时。


### 8.2 为什么占用很多磁盘空间

因为脚本会保留以下中间产物：

- raw super 镜像
- 解包后的逻辑分区镜像
- 从 ext4 分区中导出的文件树

建议至少预留几十 GB 的临时空间。


### 8.3 脚本是否需要 root

不需要。

脚本不通过 `mount` 挂载镜像，而是使用：

- `lpunpack`
- `debugfs`
- `dumpe2fs`

直接读取镜像内容。


### 8.4 为什么 `file` 识别失败

常见原因：

- `file` 二进制存在，但没有对应的 `magic.mgc`
- `FILE` 环境变量指向的不是正确可执行文件

建议：

- 优先使用系统自带 `file`
- 或者显式设置 `MAGIC=/path/to/magic.mgc`


## 9. 适用场景

该脚本适合以下场景：

- 两个版本之间 `super.img` 变大原因分析
- CI 构建产物的动态分区大小对比
- 重点追踪 `system`、`vendor`、`product`、`system_ext` 的变化来源
- 快速定位新增大 APK、大 SO、大模型文件、大媒体资源


## 10. 当前脚本路径

当前脚本位于：

```text
./super_image_diff.py
```

