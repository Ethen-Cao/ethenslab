+++
date = '2025-09-22T12:11:50+08:00'
draft = false
title = 'contents.xml 属性与字段说明文档'
+++

## `contents.xml` 属性与字段说明文档

### 1. 文档引言

`contents.xml` 文件是高通（Qualcomm）平台 Meta-Build 系统的核心配置文件。它作为一个**元构建清单 (Meta-Build Manifest)**，以声明式 XML 的格式，精确定义了一个完整软件包从源代码到最终刷机包的**所有环节**。

本说明文档旨在为开发者提供一份详尽的参考，解释 `contents.xml` 文件中各个 XML 标签、属性及字段的含义，帮助开发者理解、调试和定制复杂的构建流程。

---

### 2. 顶层结构标签

`contents.xml` 由多个顶层标签构成，每个标签负责一部分核心功能。

| 标签 | 含义 |
| :--- | :--- |
| `<product_flavors>` | 定义产品的不同“风味”或变种。 |
| `<product_info>` | 提供关于产品的元数据信息。 |
| `<partition_info>` | 定义与分区操作相关的信息。 |
| `<builds_flat>` | **核心部分**，定义所有独立软件组件的构建信息。 |
| `<build_tools>` | （可选）定义构建系统内部使用的工具。 |
| `<external_tools>` | 声明构建或调试过程中依赖的外部工具。 |
| `<workflow>` | 定义构建完成后的自动化处理与打包流程。 |

---
### 3. 标签与属性详解

#### **3.1 `<product_flavors>` 区域**

此区域用于定义不同的产品形态。

- **`<product_flavors cmm_pf_var="...">`**
  - **属性**: `cmm_pf_var`
  - **含义**: 定义一个变量名，该变量用于在 CMM (常用于 Trace32 调试器) 脚本中存储当前选择的产品风味（Product Flavor）。构建系统会根据用户选择的风味（如 `8155_la`）为这个变量赋值。

#### **3.2 `<product_info>` 区域**

此区域提供构建的元数据信息。

- **`<chipid flavor="..." cmm_var="...">`**
  - **属性**: `flavor`
  - **含义**: 建立产品风味与特定芯片 ID 之间的映射关系。这使得构建系统知道 `8155_la` 风味对应的是 `SDM855` 芯片。
  - **属性**: `cmm_var`
  - **含义**: 定义一个 CMM 脚本变量名。构建系统会将该标签的值赋给这个变量，供外部工具（尤其是 Trace32）使用。

#### **3.3 `<partition_info>` 区域**

此区域定义与分区操作相关的信息。

- **`<partition fastboot_erase="...">`**
  - **属性**: `fastboot_erase`
  - **含义**: 一个布尔属性 (`true`/`false`)，用于告知 `fastboot` 刷机工具，在烧录此分区前是否应先执行擦除 (`erase`) 操作。
  - **适用场景**: 通常用于 `modemst1`, `modemst2`, `fsg` 等存储校准数据的分区，确保刷入新固件时不会被旧数据干扰。

#### **3.4 `<builds_flat>` 区域 (核心)**

这是文件最核心、最复杂的部分，定义了所有组件的详细构建信息。其下的 `<build>` 标签包含了丰富的子标签和属性。

##### **`<download_file>` 标签**
定义需要烧录到设备的具体文件及其烧录规则。

| 属性 | 含义 | 示例值 |
| :--- | :--- | :--- |
| `fastboot` / `fastboot_complete` | 指定 `fastboot` 模式下烧录的目标分区名。 | `boot_a` |
| `backup_partition` | 在 A/B 系统中，指定主分区对应的备份分区名。 | `boot_b` |
| `minimized` | 标记此文件是否属于“最小化构建”的一部分 (`true`/`false`)。 | `true` |
| `ignore` | 如果为 `true`，构建系统在处理烧录任务时会忽略此文件。 | `true` |
| `pil_split` | 标记该文件是用于 PIL 子系统的固件，需要被 `pil-splitter.py` 处理。 | `adsp` |
| `sparse_image_path` | 标记该文件是一个稀疏镜像 (`true`/`false`)。 | `true` |
| `gpt_file` | 用于多 LUN 存储，指示该 GPT 文件应用于哪个存储单元。 | `partition:0` |
| `cmm_file_var` | 为该文件在 CMM 脚本中定义一个变量名。 | `APPSBOOT_BINARY` |

##### **`<file_ref>` 标签**
引用一个文件，该文件是构建过程的一部分，但不一定直接烧录。

| 属性 | 含义 | 示例值 |
| :--- | :--- | :--- |
| `raw_partition` | 标记该 XML 文件是定义存储分区的“原始”配置文件 (`true`/`false`)。 | `true` |
| `fat_file_*` | 模式匹配属性，标记该文件应被打包进一个 FAT 格式镜像中。 | `true` |
| `*so_signed` | 标记该文件是需要特殊签名的动态库 (`.so`) (`true`/`false`)。 | `true` |

##### **`<device_programmer>` 标签**
定义用于 EDL 模式刷机的 Firehose 程序。

| 属性 | 含义 | 示例值 |
| :--- | :--- | :--- |
| `firehose_type` | 指定 Firehose 程序的类型。 | `ddr`, `lite` |

---
#### **3.5 `<workflow>` 区域**

定义构建后期的自动化处理流程。

- **`<step filter="..." type="..." storage_type="..." flavor="...">`**
  - **属性**: `filter`
  - **含义**: 步骤过滤器。构建系统可以按 `filter` 运行特定类别的步骤，如 `partition`, `hlos`, `non_hlos`。
  - **属性**: `type`
  - **含义**: 定义该步骤的操作类型，如 `exec` (执行), `copy` (复制), `delete` (删除)。
  - **属性**: `storage_type`
  - **含义**: 允许为不同的存储类型（如 `ufs` 或 `emmc`）定义不同的工作流步骤。
  - **属性**: `flavor`
  - **含义**: 限定此步骤仅在构建指定的产品风味时执行。

---
### 4. 总结

`contents.xml` 通过其丰富而精确的属性与字段集，为高通平台的复杂软件构建提供了强大的声明式控制能力。理解这些定义是掌握整个构建系统、进行高效开发和问题排查的基础。本文档旨在作为一份快速参考，帮助开发者清晰地认知其结构与含义。