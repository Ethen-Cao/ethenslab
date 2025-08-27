+++
date = '2025-08-27T11:36:11+08:00'
draft = false
title = '高通平台 Widevine L1 认证实施流程'
+++

## 整体流程

![](/ethenslab/images/widevine-L1-verification-process.png)

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

👉 对于 **OEM 车厂的 IVI 设备**，如果目标是 **Widevine L1 认证**：

* **一定需要经过 Google 授权的第三方实验室执行正式测试**，实验室测试结果 + Google 审核 才能最终获得 L1 证书与生产 Keybox。
* OEM 内部自测只能作为预演和问题排查，不能替代正式认证。

---

