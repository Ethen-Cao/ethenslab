+++
date = '2025-08-27T11:36:11+08:00'
draft = false
title = '高通平台 Widevine L1 认证实施流程'
+++

## 整体流程

![](/ethenslab/images/widevine-L1-verification-process.png)


1. **项目启动与平台选型**

   * OEM（整车厂）根据车型、市场需求和 DRM 策略，决定采用 Widevine L1。
   * 高通提供支持 L1 的硬件平台（SoC + TEE），并交付 BSP/SDK 及安全方案指导。

2. **软件集成与安全路径实现**

   * OEM 集成 Android OS、Chromium 和 Android DRM 框架。
   * 通过调用 MediaDrm/CDM API 实现播放功能。
   * 高通协助 OEM 完成安全视频路径 (SVP) 与安全音频路径 (SAP)，并提供 TrustZone、Keymaster、OEMCrypto 的技术支持。

3. **Widevine Partner Portal 注册与工具获取**

   * OEM 向 Google 申请 Widevine Partner Portal 访问权限。
   * Google 提供 L1 安全规范文档、测试工具及测试用例，并下发测试用 Device Keybox（仅限开发与自测）。

4. **内部自测与预认证准备**

   * OEM 搭建 L1 测试环境并运行 Google L1 Test Suite，进行自测验证。
   * 高通协助分析结果并解决安全相关问题，为正式认证做准备。

5. **正式认证测试（由授权实验室执行）**

   * OEM 将待测设备及自测结果提交至 Google 授权实验室（3PL）。
   * 实验室使用 Google 官方 L1 Test Suite 执行测试，并将测试结果与报告上传至 Google。

6. **Google L1 认证审核**

   * Google 审核实验室提交的结果和报告。
   * 重点审核 TEE（TrustZone）、OEMCrypto、SVP/SAP 等安全实现。
   * 可能要求进行安全漏洞扫描或代码审计，并在必要时与 OEM 和高通进行技术澄清。

7. **颁发 L1 证书与生产 Keybox**

   * 若认证通过：Google 向 OEM 颁发 Widevine L1 证书和设备特定的 **生产 Keybox**。
   * 若认证失败：Google 提供失败原因和改进建议，OEM 需回到开发或自测阶段进行修正后重新提交。

8. **量产集成与最终验证**

   * OEM 将 Widevine L1 证书和生产 Keybox 集成到量产软件中。
   * 执行最终的功能验证和回归测试，确保 DRM 功能正常工作。
   * 完成量产准备。

---

### **1. OEM（整车厂 / 汽车厂商）**

* **角色定位**：最终责任方，认证是以 **整车或IVI设备产品** 为目标。
* **职责**：

  * 决定是否上马 Widevine L1 项目。
  * 向 Google 提交认证申请，作为主要签署方。
  * 提供测试样机给实验室。
  * 确保整车或IVI系统满足 Google 的安全要求（TEE, Keymaster, HDCP, DRM pipeline 等）。
* **典型互动**：

  * 向 Tier1 厂商提出需求。
  * 与 Google 签署相关协议。
  * 最终对认证结果负责。

---

### **2. Tier1（一级供应商 / 车机厂）**

* **角色定位**：为 OEM 提供 **IVI硬件/软件解决方案**。
* **职责**：

  * 基于 Qualcomm 平台（或其他SoC）开发 IVI 系统。
  * 集成 Widevine DRM 相关组件（CDM, HAL, Secure OS）。
  * 协助 OEM 处理认证流程中的问题。
  * 提供调试、修复、合规性实现。
* **典型互动**：

  * 与 Qualcomm 合作调通 DRM stack。
  * 与实验室沟通测试中发现的问题。
  * 提交结果给 OEM 汇总。

---

### **3. Qualcomm（芯片厂 / 平台厂商）**

* **角色定位**：提供底层 SoC 平台和安全执行环境 (TEE, TrustZone)。
* **职责**：

  * 提供 Widevine L1 的参考实现（CDM 安全库、Secure Processor 固件）。
  * 保证硬件层安全特性（HDCP, Secure Video Path, Key ladder）。
  * 向 Tier1 提供 BSP（Board Support Package）和 DRM 相关驱动。
* **典型互动**：

  * 向 OEM/Tier1 提供 L1-capable 平台。
  * 参与 debug，但认证主体不是 Qualcomm。

---

### **4. Lab（第三方授权实验室）**

* **角色定位**：Google 授权的独立实验室，负责执行 **正式认证测试**。
* **职责**：

  * 按照 Google 提供的 Test Plan 执行测试。
  * 确认设备是否满足 Widevine 安全和性能要求。
  * 出具测试报告提交给 Google。
* **典型互动**：

  * 与 OEM/Tier1 沟通测试流程、收样。
  * 测试不通过时，要求整改并复测。

---

### **5. Google（Widevine Owner）**

* **角色定位**：标准和认证的最终裁决者。
* **职责**：

  * 定义 Widevine L1 技术要求和安全模型。
  * 授权实验室。
  * 审核实验室测试报告并决定是否颁发认证。
* **典型互动**：

  * 与 OEM 签署协议。
  * 只与实验室保持正式沟通（大部分情况下不会直接与 Tier1/Qualcomm 一对一沟通）。

---

### **关系总结**

* **OEM**：项目 Owner & 最终认证主体。
* **Tier1**：具体实现方 & 集成支持。
* **Qualcomm**：提供 SoC & 底层 Widevine 能力。
* **Lab**：执行测试 & 出报告。
* **Google**：制定标准 & 最终发证。

**关键点**：

* 认证主体是 **OEM**，不是 Tier1 或 Qualcomm。
* 测试必须通过 **Google 授权的 Lab**。
* Qualcomm 提供平台支持，但不会替 OEM/Tier1 去认证。

---


## 认证实验室

下面是目前已知的 Widevine L1 正式认证中，**由授权实验室（Widevine 3PL，即 Third-Party Labs）执行正式测试** 的一些主要合作伙伴名单：

---

### Widevine 授权第三方实验室（3PL）名单

根据 Google 官方资料，“Widevine 3PL 计划允许经授权的第三方合作伙伴协助执行设备集成和认证流程” ([widevine.com][1])。目前公开列出的合作伙伴包括：

* **AltiMedia**
* **castLabs**
* **Irdeto**
* **Seirobotics**
* **Smartlabs.tv** ([widevine.com][1])

这些实验室具备 Google 的授权，可执行如下关键事项：

* 执行 Widevine 测试计划（Test Suite）并提交测试结果至 Google
* 协助 OEM／SoC 厂商进行产品开发和集成支持
* 提供固件更新与后续维护相关协助 ([widevine.com][1])


---

### 具体案例说明

* **castLabs** 不仅是认证测试实验室，同时也为硬件厂商或应用开发商加速 Widevine 认证流程，他们提供设备注册、CDM 功能测试、Keybox 请求支持，并协助加速官方认证流程 ([castLabs][2])。

---

### 简要总结与建议

| 实验室名称        | 角色与服务内容                |
| ------------ | ---------------------- |
| AltiMedia    | 执行测试并提交结果，支持整车厂/SoC 集成 |
| castLabs     | 广泛技术支持 + 加速认证服务        |
| Irdeto       | 参与第三方测试与集成支持           |
| Seirobotics  | 提供 Widevine 3PL 服务     |
| Smartlabs.tv | 提供 Widevine 官方授权测试与支持  |

---

[1]: https://www.widevine.com/solutions/widevine-3pl?utm_source=chatgpt.com "Widevine Third Party Labs (3PL)"
[2]: https://castlabs.com/widevine-certification/?utm_source=chatgpt.com "Widevine CDM Device & App Certification - castLabs"

## OEM 汽车厂商在 IVI 设备上获得 Widevine 认证时，第三方实验室（3PL）的作用和必要性

这个问题非常关键 ⚡，我帮你拆解一下 **OEM 汽车厂商在 IVI 设备上获得 Widevine 认证时，第三方实验室（3PL）的作用和必要性**：

---

### 1. Widevine 认证的本质

* **Widevine L1/L3 认证** 是 Google 管控的安全合规流程。
* 认证的目标是确认设备（含 SoC、TEE、OEMCrypto、Secure Path 等）能够满足 Google 的安全规范，保证密钥、视频数据在传输和解码过程中不被泄露。
* **最终的认证权威是 Google**，而不是 OEM、自测或 SoC 厂商。

---

### 2. 第三方实验室（3PL）的角色

Google 本身并不会亲自测试每个 OEM 设备，而是通过 **授权的第三方实验室（3PL, Third-Party Lab）** 来执行认证测试和结果验证。

* 实验室会使用 **Google 提供的官方 L1 Test Suite** 在真实设备上执行测试。
* 测试结果会直接反馈给 Google，Google 根据实验室结果 + 安全审查，决定是否颁发 L1 证书和生产 Keybox。
* 实验室在流程中的作用类似 **公证人/审计人**，保证测试环境和结果的客观性。

---

### 3. OEM 是否可以绕过实验室？

* **不能完全绕过。**
  OEM 可以在内部自测（预认证），但这个结果 **不能直接作为正式认证依据**。
* Google 要求 **正式认证必须通过授权实验室执行**，否则不会承认测试结果。
* 即使你是大厂（比如大众、丰田、特斯拉），也必须把设备送去 3PL 实验室完成正式测试。

---

### 4. 例外或特殊情况

* **SoC 厂商的预认证**：比如高通、联发科等会对其参考平台做过预认证，这样 OEM 在用这些 SoC 时会少一些测试项，但仍然需要把自己的整机设备送到实验室完成完整性测试。
* **L3 认证**：某些低等级（L3）设备，认证流程可能简化，有时 Google 允许直接提交测试结果。但对 **车载 IVI 设备**（涉及流媒体版权、Netflix/Disney+/YouTube），几乎都要求 L1，因此必须走实验室流程。

---

### 5. 结论 ✅

对于 **OEM 车厂的 IVI 设备**，如果目标是 **Widevine L1 认证**：

* **一定需要经过 Google 授权的第三方实验室执行正式测试**，实验室测试结果 + Google 审核 才能最终获得 L1 证书与生产 Keybox。
* OEM 内部自测只能作为预演和问题排查，不能替代正式认证。

---

