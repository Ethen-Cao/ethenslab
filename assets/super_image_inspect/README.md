# super_image_inspect

`super_image_inspect` 是一个单图分析工具，用来检查单个 Android `super.img`，输出标准化 `manifest.json` 和可直接阅读的 `summary.md`。

适用场景：

- 分析一个版本的 `super.img` 当前到底装了什么
- 查看动态分区布局、大小、已用空间和剩余空间
- 识别各分区中的 `apk`、`so`、`model_data`、`media` 等内容占比
- 为后续的 diff 工具和趋势分析生成标准基线


## 功能概览

当前版本支持：

- 自动识别 sparse super 和 raw super
- 解析动态分区 metadata
- 解包逻辑分区镜像
- 检测分区文件系统类型
- 对 ext-family 分区统计已用空间
- 在 `full` 模式下递归扫描文件并输出：
  - 全局分类汇总
  - 分区分类汇总
  - Top 目录
  - Top 文件

当前实现不依赖 `mount`，也不需要 root。


## 目录结构

```text
super_image_inspect/
  README.md
  pyproject.toml
  docs/
    requirements.md
    architecture.md
  super_image_inspect/
    __main__.py
    analyzer.py
    classify.py
    models.py
    reporting.py
    tooling.py
```


## 运行依赖

### Python

需要：

- `python3 >= 3.9`

脚本只使用标准库，不需要 `pip install` 第三方 Python 包。


### 外部命令

按模式区分依赖：

`metadata` 模式需要：

- `simg2img`
- `lpdump`

`summary` 模式额外需要：

- `lpunpack`
- `file`
- `dumpe2fs`

`full` 模式额外需要：

- `debugfs`


## 工具查找顺序

程序按以下顺序查找外部工具：

1. 环境变量
2. `--tool-dir`
3. 工程根目录
4. 工程根目录下的 `tools/`
5. 系统 `PATH`
6. 代码中预置的若干候选路径

支持的环境变量：

- `SIMG2IMG`
- `LPDUMP`
- `LPUNPACK`
- `DEBUGFS`
- `DUMPE2FS`
- `FILE`


## 安装方式

### 方式 1：直接在源码目录运行

这是最简单的方式：

```bash
cd /home/voyah/ethenslab/assets/super_image_inspect
python3 -m super_image_inspect /path/to/super.img
```


### 方式 2：安装命令行入口

如果想使用 `super-image-inspect` 命令，可以在工程目录下执行：

```bash
cd /home/voyah/ethenslab/assets/super_image_inspect
python3 -m pip install -e .
```

安装后可直接运行：

```bash
super-image-inspect /path/to/super.img
```


## 快速开始

### 1. 只看 metadata

适合快速确认 super 基本布局：

```bash
python3 -m super_image_inspect /path/to/super.img --mode metadata --workdir ./analysis_output
```


### 2. 分区级摘要分析

适合查看分区镜像大小、文件系统类型和已用空间：

```bash
python3 -m super_image_inspect /path/to/super.img --mode summary --workdir ./analysis_output
```


### 3. 完整分析

适合查看分类汇总、Top 目录和 Top 文件：

```bash
python3 -m super_image_inspect /path/to/super.img --mode full --workdir ./analysis_output
```


### 4. 仅深扫指定分区

适合大镜像场景，避免所有分区都做递归扫描：

```bash
python3 -m super_image_inspect /path/to/super.img \
  --mode full \
  --partition system \
  --partition vendor \
  --top 20 \
  --workdir ./analysis_output
```


### 5. 指定工具目录

如果你把 host 工具和脚本放在同一目录或单独目录中，可以这样运行：

```bash
python3 -m super_image_inspect /path/to/super.img \
  --mode full \
  --tool-dir /path/to/tools \
  --workdir ./analysis_output
```


## CLI 参数

```text
python3 -m super_image_inspect SUPER_IMG [options]
```

主要参数：

- `super_img`
  - 输入的 `super.img` 路径
- `--workdir`
  - 工作目录，保存 raw 镜像、中间产物和最终报告
- `--mode {metadata,summary,full}`
  - 分析深度
- `--top`
  - 输出 Top N 项
- `--partition`
  - 仅在 `full` 模式下深扫指定分区，可重复
- `--tool-dir`
  - 指定外部工具目录
- `--bucket-depth`
  - 目录聚合深度，默认 `2`


## 三种模式的区别

### `metadata`

特点：

- 最快
- 只做 super metadata 解析
- 不解包逻辑分区

适合：

- 确认有哪些动态分区
- 快速拿 `super total/used/free`


### `summary`

特点：

- 解包逻辑分区镜像
- 识别文件系统类型
- 对支持的 ext-family 分区统计 filesystem usage
- 不做递归文件扫描

适合：

- 看每个逻辑分区多大
- 看各分区已用空间和剩余空间


### `full`

特点：

- 包含 `summary` 的全部内容
- 对支持的 ext-family 分区执行递归文件扫描
- 输出分类汇总、目录汇总和 Top 文件

适合：

- 深入定位大 APK、大 SO、大模型文件、大资源
- 产出单图基线，供后续 diff 工具使用


## 输出目录

假设使用：

```bash
python3 -m super_image_inspect /path/to/super.img --workdir ./analysis_output
```

则输出目录结构如下：

```text
analysis_output/
  raw/
  layout/
  unpacked/
  fs/
  reports/
```

说明：

- `raw/`
  - sparse super 转换后的 raw super
- `layout/`
  - `lpdump -j` 导出的 metadata JSON
- `unpacked/`
  - `lpunpack` 导出的逻辑分区镜像
- `fs/`
  - `full` 模式下通过 `debugfs` 导出的文件树
- `reports/`
  - 最终报告


## 报告文件说明

### 必定输出

- `reports/manifest.json`
  - 机器可读标准输出
- `reports/summary.md`
  - 人类可读汇总报告
- `reports/partition_summary.csv`
  - 分区摘要表


### `full` 模式下通常还会输出

- `reports/global_category_summary.csv`
- `reports/partition_category_summary.csv`
- `reports/global_bucket_summary.csv`
- `reports/top_files.csv`


## 关于 `shared_blocks_detected`

当报告里出现：

- `shared_blocks_detected = True`

表示该分区文件系统启用了块共享特性。此时：

- `apparent_size_total`
  - 表示文件逻辑大小总和
- `fs_used_bytes`
  - 表示文件系统实际物理占用

因此在这类分区里，可能出现：

```text
apparent_size_total > fs_used_bytes
```

这是正常现象，不表示脚本计算错误。

原因是：

- 多个文件可以共享同一批物理数据块
- 逻辑大小会按文件分别累计
- 物理块只会实际计算一次

所以：

- `category` 汇总
- `bucket` 汇总
- `top_files`

这些都是“逻辑大小视角”

而：

- `fs_used_bytes`

才是“物理占用视角”


## 控制台输出示例

执行完成后，控制台会输出摘要，例如：

```text
super image inspect summary
mode             : full
input super      : /path/to/super.img
is sparse        : True
sparse size      : 8980582596 (8.36 GiB)
raw size         : 32212254720 (30.00 GiB)
super used size  : 9010159616 (8.39 GiB)
super free size  : 23202095104 (21.61 GiB)
partitions       : 6
reports          :
  manifest: ...
  summary: ...
```


## 常见使用方式

### 快速确认某个 super 是否接近装满

```bash
python3 -m super_image_inspect /path/to/super.img --mode metadata
```

重点看：

- `super used size`
- `super free size`


### 只想看各分区实际使用量

```bash
python3 -m super_image_inspect /path/to/super.img --mode summary
```

重点看：

- `partition_summary.csv`
- `summary.md`


### 只想看 `system` 和 `vendor`

```bash
python3 -m super_image_inspect /path/to/super.img \
  --mode full \
  --partition system \
  --partition vendor
```


## 当前限制

当前版本已支持：

- super metadata 解析
- ext-family 分区深度扫描

当前版本的限制：

- 暂未对 `erofs` 做深度文件扫描
- `full` 模式会占用较多时间和磁盘空间
- 文件分类规则目前是代码内置规则，不是外部配置文件


## 相关文档

- 需求文档：[docs/requirements.md](./docs/requirements.md)
- 架构设计：[docs/architecture.md](./docs/architecture.md)


## 开发者自检

语法检查：

```bash
python3 -m compileall super_image_inspect
```

查看帮助：

```bash
python3 -m super_image_inspect --help
```
