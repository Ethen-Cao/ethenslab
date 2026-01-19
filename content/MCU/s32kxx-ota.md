# S32K324 MCU OTA A/B Swap 机制系统设计文档（System Design Specification）

> **适用对象**：NXP S32K324（S32K3 系列）
> **升级链路假设**：SoC 通过 **SPI** 向 MCU 下发升级镜像；MCU 将新镜像写入 **Passive（B）** 区域；通过 **HSE A/B Swap** 在复位后完成映射切换并启动新镜像。
> **已知约束**：Bootloader **不在 swap 区域内**；B 区物理地址范围与链接地址 **TBD**。
> **术语说明**：本文“分区 A/B”指 **Flash 双镜像（Active/Passive block remapping）**，非 Linux 分区表概念。

---

## 0. 文档控制

* 文档编号：SDS-S32K324-OTA-ABSWAP-001
* 版本：v0.9（Draft）
* 状态：Draft
* 作者：TBD
* 评审人：TBD
* 生效日期：TBD

### 变更记录

| 版本   | 日期  | 变更说明                         | 作者  |
| ---- | --- | ---------------------------- | --- |
| v0.9 | TBD | 初版：定义 OTA、A/B swap、回滚策略与排障流程 | TBD |

---

## 1. 引言

### 1.1 目的

定义 S32K324 上 **OTA + A/B Swap** 的端到端机制：镜像传输、写入、校验、切换、试运行确认、回滚触发条件与实现要点，并提供“切 B 成功但不启动”的应对流程。

### 1.2 范围

* **包含**：SPI 升级协议（概念级）、镜像格式（概念级）、Flash 写入/校验流程、Bootloader/BootManager 策略、与 HSE A/B Swap 的集成点、回滚与诊断。
* **不包含（TBD/Out of Scope）**：

  * HSE Secure Boot/SMR map 的具体配置细节（通常依赖 HSE FW RM/示例与项目密钥体系）。
  * 具体 Flash block 地址、块大小、B 区起始地址/长度、应用链接脚本细节（均标记 TBD）。

### 1.3 参考资料

* NXP OTA A/B Swap 演示材料（active/passive block、复位后映射切换、rollback 说明）([NXP Community][1])
* AN13388 S32K3 Memories Guide（program/erase 最小粒度、对齐、ECC、写前需擦除、最小 sector）([NXP Community][2])
* AN13414 Migration Guidelines（active/passive blocks、flash remapping、A/B swap 支持“backup firmware rollback / seamless update”）([nxp.com][3])
* NXP Community：S32K3 bank switching/A-B swap 由 HSE FW 支持；bootloader 复位后决策运行哪个应用 ([NXP Community][4])
* NXP TechSupport：A/B swap **不会自动回滚**，需用户请求；镜像损坏场景需 advanced secure boot + alternate pre-boot SMR map 才能在校验失败时执行备用镜像 ([NXP Community][5])
* S32K3xx Security Training：HSE/secure BAF 安装与 A/B swap 配置相关说明（“A/B swap activation is definitive”等）([NXP Community][6])

### 1.4 术语与缩写

* **Active/Passive Block**：当前运行镜像所在块 / 备用写入块。([nxp.com][3])
* **A/B Swap**：通过 HSE 在复位后将 passive 映射为 active（低地址空间），实现无拷贝切换。([NXP Community][1])
* **BCB**（Boot Control Block）：引导控制块（slot、trial、confirm、失败计数、校验摘要等）。
* **Trial/Confirm**：试运行/确认机制（未确认则回滚）。
* **HSE/MU**：Host Security Engine / Messaging Unit（host 与 HSE 通信接口）。([NXP Community][6])

---

## 2. 总体概述

### 2.1 系统目标

1. 支持从 SoC 通过 SPI 对 MCU 应用固件进行 OTA 更新。
2. 使用 **Active/Passive + Flash remapping + A/B swap** 实现：写 B、复位切换、试运行确认、失败回滚。([nxp.com][3])
3. 在镜像损坏/无法启动时，系统能够**自动或半自动**恢复到可运行镜像（A）。

### 2.2 关键设计原则

* **Bootloader 不在 swap 区域内**：确保无论 A/B 哪一侧损坏，仍有稳定代码可执行回滚/恢复。([NXP Community][4])
* **A/B 镜像必须满足 remapping 运行模型**：复位后 passive 变 active 并映射到低地址空间，新固件从相同逻辑起点执行。([NXP Community][1])
* **回滚不是“自动发生”**：需 Bootloader/用户逻辑显式触发 swap 回退；镜像损坏时若需“预启动自动兜底”，需引入 advanced secure boot 机制。([NXP Community][5])

---

## 3. 系统架构

### 3.1 组件划分

* **SoC OTA Client**

  * 获取升级包、拆分为 chunks、通过 SPI 发送、重传控制、最终提交。
* **MCU Bootloader/BootManager（非 swap 区域）**

  * SPI 接收升级流、写入 passive（B）区域、校验、写入 BCB、请求 HSE swap、复位。
  * 启动时读取 BCB + reset reason，执行 trial/confirm 判断与回滚请求。
* **MCU Application（A/B 双镜像，位于 swap 区域）**

  * 正常业务逻辑；在试运行成功后写 confirm。
* **HSE Firmware**

  * 提供 A/B swap（bank switching/remapping）能力；与 Host 通过 MU 通信。([NXP Community][4])
* **Flash（PFlash/DFlash）**

  * PFlash：应用镜像 A/B（Active/Passive blocks）
  * DFlash 或预留 PFlash sector：BCB、事件计数、日志等（推荐双副本）。

### 3.2 典型流程（摘要）

1. A 运行时，Bootloader 接收 SoC 下发镜像并写入 passive blocks（B）。
2. 写完后复位，复位后 passive blocks 变 active 并映射到低地址空间，新镜像执行。([NXP Community][1])
3. 若新镜像无法启动/未确认，Bootloader 依据策略请求 swap 回 A（回滚）。
4. 若需要“镜像损坏导致无法进入应用/甚至无法执行回滚代码”的自动兜底，引入 secure boot 的备用验证图执行备用镜像。([NXP Community][5])

---

## 4. 存储与内存布局（TBD 驱动）

> **说明**：S32K3 OTA demo 用“blocks 0&1 active / blocks 2&3 passive”的示例描述 A/B 切换。([NXP Community][1])
> S32K324 的实际 block 划分、A/B 容量、起始地址、对齐与保护策略需基于项目 flash 配置最终确认（本节大量 TBD）。

### 4.1 Flash 分区（逻辑）

* **Bootloader Region（Non-swap）**

  * 起始地址：TBD
  * 大小：TBD（建议 ≥ 64KB，含 SPI/Flash/HSE/MU/诊断/恢复模式）
  * 属性：只读/受保护（生产态）。
* **Swap Region（Application NVM）**

  * **Active Block（A）**：TBD（blocks TBD）
  * **Passive Block（B）**：TBD（blocks TBD）
  * 约束：A/B 镜像容量相同（或满足 HSE swap 的等分要求，依实际配置 TBD）。
* **BCB & Diagnostics Region**

  * 推荐：DFlash（如可用）或预留 PFlash sectors（最小 erase 单位为 sector）。([NXP Community][2])
  * 地址/大小：TBD（至少 2 个 sector，支持双副本）。

### 4.2 链接地址（Vector Table 逻辑基址）

* **应用链接脚本中的逻辑基址**：TBD
* 设计要求：无论镜像实际写在哪个物理 block，复位后都应以 **同一逻辑起点**执行（因为 remapping 将 active 映射到低地址空间）。([NXP Community][1])

---

## 5. 需求规格

### 5.1 功能需求（Functional Requirements）

**FR-01 OTA 传输**

* MCU 应支持通过 SPI 从 SoC 接收升级包，支持分片（chunk）传输、乱序拒绝、丢包重传。
* MCU 应能在升级过程中向 SoC 回报进度（已写 offset、剩余长度、错误码）。

**FR-02 镜像完整性校验**

* MCU 必须对每个 chunk 执行传输校验（CRC16/CRC32），校验失败不得写入 Flash。
* MCU 必须在写入完成后对整个 B 镜像执行最终校验（CRC32 或 HASH），与 manifest 对比一致才允许进入切换流程。

**FR-03 Flash 写入与一致性**

* MCU 写 Flash 时必须满足最小 program 粒度、对齐与“写前擦除”规则。([NXP Community][2])
* MCU 应在写入阶段检测 program/erase 错误并中止升级，回报 SoC 错误原因。

**FR-04 A/B Swap 切换**

* MCU 在 B 镜像验证通过后，必须通过 HSE 请求 A/B swap，并触发复位，使 passive 成为 active 并映射到低地址空间执行新镜像。([NXP Community][1])

**FR-05 Trial/Confirm 试运行**

* MCU 必须支持试运行（trial）模式：切到 B 后在规定时间内由 B 镜像写入确认标志（confirm）。
* 若 B 未确认即复位或异常复位，Bootloader 必须判定试运行失败并执行回滚策略。

**FR-06 回滚（Rollback）**

* 回滚必须可由 Bootloader 显式请求：切回 A（请求 HSE swap 回退 + 复位）。
* 回滚触发条件至少包含：未确认超时、异常复位（WDG/Lockup 等）、失败计数超阈值。
* 说明：A/B swap 不会自动回滚，必须由用户逻辑请求；镜像损坏场景建议配合 secure boot 兜底。([NXP Community][5])

**FR-07 恢复模式**

* MCU 应提供“强制进入 Bootloader/强制回 A”的手段：

  * GPIO strap（TBD）、SoC SPI 命令（TBD）、连续失败次数触发（内置）。

**FR-08 诊断与可观测性**

* Bootloader 必须记录并可输出：当前 slot、trial/confirm 状态、fail_count、最后 reset reason、最后一次升级错误码、B 镜像 CRC/HASH（可选）。

---

### 5.2 非功能需求（Non-Functional Requirements）

**NFR-01 可靠性**

* 支持断电/复位恢复：任何中间态不得导致永久变砖；至少能回到 Bootloader 或可通过恢复模式重新刷写。
* BCB 必须采用双副本/日志式写入，防止写一半导致状态不可读（实现 TBD）。

**NFR-02 性能**

* OTA 传输吞吐：TBD（由 SPI 时钟、DMA、SoC/MCU 协议栈决定）
* 写入耗时：TBD（由 program/erase 粒度与校验策略决定；建议 sector 级校验可配置开关）

**NFR-03 安全**

* 支持镜像签名校验（推荐使用 HSE 能力），支持版本控制/防降级（TBD）。
* 若要求“镜像损坏时无需依赖应用确认即可自动选择备用镜像”，需启用 advanced secure boot + alternate pre-boot SMR map（TBD 配置）。([NXP Community][5])

**NFR-04 可维护性**

* 协议/状态机版本化；BCB 结构带 version 字段；错误码统一枚举。
* 支持现场日志导出（SPI 命令/串口/调试口 TBD）。

**NFR-05 功能安全（如 ISO 26262 相关）**

* 回滚策略不得引入无穷重启；应有最大重试次数与降级策略（如锁定在 Bootloader 等）。

---

## 6. 详细设计

### 6.1 SPI 传输协议（建议实现）

> chunk 大小、窗口与重传策略为可配置项，默认值 TBD（推荐从 1–4KB 起步，依据 RAM 与吞吐再优化）。

**消息类型**

* `START(manifest)`：image_size、image_version、target=B、hash、可选签名信息
* `DATA(seq, offset, len, payload, crc)`
* `END`：结束标记
* `STATUS/ACK/NACK`：状态查询、确认与重传控制
* `ABORT`：取消升级

**传输校验**

* 每个 `DATA` 必带 CRC32（或 CRC16 + 长度/offset 校验）。
* MCU：CRC 失败 → NACK（请求重传），**不得写 Flash**。

---

### 6.2 镜像与 Manifest（建议字段）

* `image_version`（单调递增，防降级 TBD）
* `image_size`
* `image_hash`（CRC32/SHA-256）
* `load_model`：AB_SWAP（运行逻辑基址固定）
* `entry_type`：vector table at logical base（TBD）
* `signature`：可选（若启用 secure boot/HSE 校验）

---

### 6.3 Flash 写入策略（必须满足 S32K3 Flash 约束）

来自 AN13388（S32K3 Memories Guide）的关键约束（写入实现必须遵守）：

* 最小 program size：**2 words = 64 bits**，且数据 **64-bit 对齐**。([NXP Community][2])
* 单次最多可 program **4 pages**（1 page=256 bits），即最多 1024 bits。([NXP Community][2])
* program 只能 **1→0**，0→1 不允许，写入前必须 erase。([NXP Community][2])
* 最小 erase 粒度为 **sector（8KB）**。([NXP Community][2])

**写入流程（建议）**

1. 升级开始前：按 B 区覆盖范围逐 sector 擦除（8KB 对齐）。([NXP Community][2])
2. 收到 chunk：在 RAM 缓冲区拼装并对齐到 64-bit；末尾不足用 0xFF padding（TBD）。
3. 分段 program：按 64-bit / page / quad-page 的策略写入（以性能与实现复杂度折中为准）。([NXP Community][2])
4. 写后校验：

   * 最低配：检查 program/erase 返回状态
   * 推荐：每个 sector 写完做一次 readback CRC；最终做整镜像 hash（开关可配）。
5. 记录进度：在 BCB 中更新 “已写最大 offset / hash rolling state”（TBD）。

---

### 6.4 与 HSE A/B Swap 集成

**能力来源**

* S32K3xx 支持 bank switching，A/B swap 由 **HSE firmware** 支持；并建议参考 demo 文档/示例。([NXP Community][4])

**切换语义（来自 OTA demo）**

* 当新镜像写入 passive blocks 后触发复位：复位后 passive blocks 变 active，映射到低地址空间执行新固件。([NXP Community][1])

**关键注意**

* A/B swap **不会自动回滚**：切回 A 必须由 Bootloader/用户逻辑再次请求 swap。([NXP Community][5])
* A/B swap 配置启用具有“永久性”含义（training 提到 activation is definitive），因此应在量产策略上谨慎规划启用时机与恢复路径。([NXP Community][6])

> **实现接口（TBD）**：HSE service ID、MU 通信细节、swap 请求 API 以项目采用的 HSE demo app/RTD 集成为准（通常来自 HSE FW package）。([NXP Community][6])

---

### 6.5 Boot Control Block（BCB）设计

**BCB（建议字段）**

* `bcb_version`
* `active_slot`：A/B
* `trial`：0/1
* `boot_success`：0/1
* `fail_count`：u8
* `image_version_A/B`
* `image_hash_B`（或 last_written_hash）
* `last_reset_reason`
* `last_error_code`
* `commit_counter`（双副本选择最新记录）

**BCB 存储策略**

* 双副本（A/B records）+ CRC32 + 单调递增 counter
* 写入采用“追加写（1→0）+ 周期性擦除”的日志型结构（如使用 RTD/FEE 可进一步简化，TBD）。([NXP Community][2])

---

## 7. 回滚机制设计

### 7.1 设计目标

* B 启动失败时：**自动回到 A**（最多 N 次尝试）。
* 避免无限重启：到达阈值后进入 Bootloader/恢复模式等待 SoC 指令。

### 7.2 回滚触发条件（建议默认）

* **RC-01 未确认超时**：trial=1 且 boot_success=0，且发生一次复位 → fail_count++
* **RC-02 异常复位**：WDG/Lockup/HF 等复位原因且处于 trial → fail_count++
* **RC-03 失败次数阈值**：fail_count ≥ 1（调试）或 ≥ 2/3（量产）→ 回滚到 A
* **RC-04 B 镜像校验失败**：写后整包 hash 不匹配 → 不允许切换（保持 A）

> 说明：若 B “镜像损坏到无法进入应用/无法执行确认逻辑”，仅靠 trial/confirm 仍能回滚（因为 Bootloader 不在 swap 区域，仍可执行回滚请求）。但若损坏导致更早阶段被 secure boot 拦截，则需 secure boot 备用验证图策略兜底。([NXP Community][5])

### 7.3 回滚执行动作

当触发回滚：

1. 更新 BCB：`active_slot=A; trial=0; boot_success=0;`（并保留诊断信息）
2. 请求 HSE swap 切回 A（TBD API）
3. 触发 system reset
4. 复位后 A 成为 active 并运行

---

## 8. “切 B 成功但不启动”应对流程（Runbook）

> 该问题在 S32K3 OTA demo 中也被频繁复现：写 B 后切换成功，但破坏 B 镜像后无法运行，官方明确 **AB swap 不会自动回滚**，需用户逻辑请求或引入 secure boot 机制。([NXP Community][5])

### 8.1 先判定：复位后有没有进入 Bootloader？

* **能进 Bootloader**（推荐路径）：

  1. 打印/上报：reset_reason、BCB(trial/boot_success/fail_count/active_slot)、HSE swap 状态（若可读）
  2. 若满足回滚条件：立即请求 swap 回 A + reset
  3. 同时保留失败现场：B 镜像 hash、最后写入 offset、最后错误码

* **进不去 Bootloader**（高危）：

  * 排查 Bootloader 是否真的“非 swap 区域且未被覆盖”（你已声明设计上如此，但需确认链接脚本/擦写范围）。
  * 若启用 secure boot：检查是否被 pre-boot verification 拦截（需要备用 SMR map 才能自动执行备份镜像）。([NXP Community][5])
  * 启用硬件恢复路径：ROM 下载模式 / 调试口（TBD，依项目硬件）。

### 8.2 最常见根因与快速验证

1. **B 镜像写入物理地址错/偏移错**

   * 对照“passive blocks”规划（TBD），抽检 B 起始处向量表是否合理。
2. **Flash 写入对齐/粒度错误导致向量表损坏**（MSP/ResetHandler 非法）

   * 核查是否严格按 64-bit 对齐与最小 program 粒度写入；是否擦除到 8KB sector 边界。([NXP Community][2])
3. **写后未校验**导致“写入静默失败”

   * 开启 sector readback CRC 或全镜像 hash 校验，定位坏区。
4. **应用链接地址模型不匹配 AB swap remapping**

   * AB swap 的目标是复位后 active 映射到低地址空间运行（无需复杂 linker tracking）。([nxp.com][3])
   * 因此 A/B 的“运行逻辑基址/向量表基址”应一致（具体基址 TBD）。
5. **试运行确认逻辑缺失**

   * B 没有写 confirm，导致系统反复尝试或停留在异常状态（需依 BCB 策略回滚）。

### 8.3 建议的“救场开关”

* Bootloader 增加 **强制回 A**：检测 GPIO strap（TBD）或 SoC 发来的 `FORCE_ROLLBACK` SPI 命令。
* fail_count 阈值：调试阶段设为 1；量产设为 2~3。
* BCB 记录最近一次 swap 请求与 swap 结果（TBD），便于现场定位“切换成功/启动失败”的边界点。

---

## 9. 安全设计（可选增强）

### 9.1 基线安全（建议）

* Manifest + hash 校验（MCU 侧必须做）
* SoC->MCU 传输链路校验（每 chunk CRC）

### 9.2 需要“镜像损坏也能自动兜底”的场景

官方建议：若希望在镜像损坏时自动采取动作，需要实现 **advanced secure boot**，并配置 **alternate pre-boot SMR verification map**：正常预启动校验失败时可执行备用镜像，由备用镜像采取回滚动作。([NXP Community][5])

> 该部分具体配置/密钥/SMR map 细节：**TBD（依 HSE FW RM 与项目安全策略）**。([NXP Community][6])

---

## 10. 测试与验证计划（摘要）

### 10.1 功能测试

* 正常 OTA：写 B → swap → B 启动 → confirm → 后续重启仍为 B
* 回滚测试：写入“故意破坏的 B” → swap → 触发 WDG/不 confirm → 回滚 A
* 断电测试：传输中断电 / 擦除中断电 / 写入中断电 / swap 前断电 / swap 后首次启动断电

### 10.2 可靠性与鲁棒性

* chunk 丢包/重复包/乱序包
* CRC 错误注入
* Flash program/erase 错误注入（模拟返回错误位）

### 10.3 安全测试（若启用）

* 签名错误镜像拒绝
* 版本回退拒绝（anti-rollback，TBD）

---

## 11. 风险与 TBD 清单

### 11.1 风险

* Bootloader 若擦写范围配置错误，可能误擦 swap 区或误擦自身导致变砖（必须加保护与白名单）。
* BCB 若无双副本与断电保护，容易出现“状态不可判定”导致启动策略异常。
* 若启用 A/B swap 配置且“activation definitive”，量产前需明确恢复路径与售后策略。([NXP Community][6])

### 11.2 TBD（待确认）

* B 区物理地址范围（blocks/起始地址/长度）
* 应用链接地址（vector table 逻辑基址）
* SPI 速率、chunk 默认大小、窗口大小、超时与重传策略
* HSE swap 请求 API/服务号/返回码（依 HSE demo/RTD 集成）([NXP Community][4])
* reset reason 获取方式与分类（WDG/lockup 等）
* 恢复模式入口（GPIO strap/ROM boot 等）

---

## 附录 A：关键实现检查表（工程落地用）

* [ ] Bootloader 链接脚本确认：不在 swap 区，擦写白名单只覆盖 passive B + BCB
* [ ] Flash 驱动确认：64-bit 对齐写入、写前 sector erase、错误位处理（PEP/解锁等）([NXP Community][2])
* [ ] 写后校验策略：至少整镜像 hash；建议加 sector readback CRC（可配）
* [ ] BCB 双副本：带 CRC + counter；断电恢复可判定最新有效记录
* [ ] Trial/Confirm：B 启动后 N 秒内 confirm；Bootloader 依据 fail_count 回滚
* [ ] “切 B 不启动”救场：强制回 A 命令/strap；fail_count=1（调试）
* [ ]（可选）Secure boot 备用验证图：镜像损坏时自动执行备用镜像并回滚 ([NXP Community][5])

---

在这份文档基础上继续补齐两块最关键的 **TBD**（并把“切 B 成功但不启动”直接收敛到可操作的排障点）：

1. S32K324 的 **Flash block 划分与 swap region 规划**（给我项目的 memory map/链接脚本片段即可）
2. 你们当前 MCU 写 Flash 的 **最小写入函数**（一次写多少、对齐要求、擦除策略、错误返回）

补齐后我还能把 **BCB 的二进制布局（字段偏移/对齐/CRC）** 和 **Bootloader 状态机伪代码**写到可直接实现的程度。

[1]: https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/S32K%40tkb/118/1/S32K3_OTA_AB_SWAP_Demostration.pdf "NXP PowerPoint Template 2020 Confidential & Proprietary"
[2]: https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/S32K/37044/2/AN13388.pdf "AN13388: S32K3 Memories Guide"
[3]: https://www.nxp.com/docs/en/application-note/AN13414.pdf "AN13414: S32K1 to S32K3 Migration Guidelines - Application Note"
[4]: https://community.nxp.com/t5/S32K/Bank-switching-for-s32k-microcontroller/m-p/1431652/highlight/true "
	Bank switching for s32k microcontroller - NXP Community
"
[5]: https://community.nxp.com/t5/S32K/How-to-enable-the-rollback-function-of-Hse-AB-SWAP-on-S32K3/td-p/2145179?profile.language=en "
	How to enable the rollback function of Hse AB SWAP on S32K3? - NXP Community
"
[6]: https://community.nxp.com/pwmxy87654/attachments/pwmxy87654/S32K/30542/2/12_S32K3xx_Security_Overview_and_Bring_Up_Training.pdf "12: S32K3xx Security Overview and Bring Up - Training"
