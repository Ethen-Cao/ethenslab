+++
date = '2025-08-25T11:36:11+08:00'
lastmod = '2026-09-29'
draft = false
title = 'Chromium + Android Widevine：L1/L3 选择与视频播放架构'
+++

## 概述

在 Android 端的 Chromium (或 WebView) 中播放受 Widevine 保护的加密视频，涉及到网页前端 (JavaScript EME API)、浏览器内核 (Chromium Media)、Android 原生媒体框架 (MediaDrm / MediaCodec) 以及底层安全环境 (TEE) 的多方协同。

本文档梳理了 Chromium 在 Android 上处理 Widevine DRM 的核心交互流程，重点解析 **L1/L3 安全等级的协商机制**、**会话生命周期** 以及 **排错指南**。

> [!NOTE]
> 设备硬件支持 Widevine L1，并不意味着每次网页播放都会自动启用 L1。实际使用的安全等级由**网页播放器提出的候选配置**、**Chromium 的安全策略约束** 以及 **Android 框架能力** 共同协商决定。

## 参与者与职责边界

在完整的 DRM 播放链路中，各参与者的职责界限明确：

| 参与者 | 职责 |
| :--- | :--- |
| **网站业务后台** | 提供播放器前端代码、视频 Manifest 以及内容授权策略。 |
| **网页播放器 (JS)** | 通过 EME (Encrypted Media Extensions) API 请求 DRM 能力、创建和绑定对象、处理 DRM 消息、向 License 服务器发起网络请求。 |
| **Chromium / WebView** | 响应网页 EME 请求，综合系统 DRM 能力、编码格式和安全约束进行配置选择，并负责桥接 Android 原生 `MediaDrm` 接口。 |
| **MediaDrm / Widevine CDM** | Android 框架层的 DRM 接口与底层 CDM 插件。负责管理原生 DRM 会话、生成 Challenge、解析 License 并强制执行内容使用限制。 |
| **MediaCrypto / MediaCodec** | 将解码器与 DRM 会话关联。安全解码 (Secure Decode) 路径下，解密与解码均在底层安全硬件中进行。 |
| **License Server** | 处理客户端的 DRM 请求，验证身份与授权策略，下发包含内容密钥 (Content Key) 的 License。 |

## DRM 会话与播放时序

完整的 DRM 播放协商通常包含以下关键阶段。

![Android Chromium 与 Widevine 配置协商时序图](../../../static/images/chromium-drm.png)
*(查看可缩放的 [SVG 图](/ethenslab/images/chromium-drm.svg) · [PlantUML 源码](/ethenslab/images/plantuml/chromium-drm.puml))*

### 1. 播放策略与 L1/L3 配置协商

网站前端通过调用 `navigator.requestMediaKeySystemAccess(keySystem, configs)` 发起配置请求，提交包括音视频编码格式、`robustness`（鲁棒性要求）、会话类型等候选数组。

Chromium 会按照网页给出的候选顺序，结合底层 Android 系统的实际能力进行检查验证，并选择**首个满足条件**的配置。若全部不满足，则抛出异常拒绝请求。

在 Android Chromium 的实现路径中，L1/L3 的最终裁定受 `use_hw_secure_codecs` 标志位影响：
* 当配置要求且系统支持硬件安全解码时，`use_hw_secure_codecs = true`，走 **L1 路径**。
* 否则 `use_hw_secure_codecs = false`，走 **L3 路径**（软解密）。

**常见候选要求映射：**

| JS `robustness` 字段 | 在 Android Chromium 实现中的映射 |
| :--- | :--- |
| 空值 或 `SW_SECURE_CRYPTO` | 不强制要求硬件安全解密；在没有其他硬件约束时，通常回退到 **L3**。 |
| `SW_SECURE_DECODE` 及以上 | 强制要求硬件安全解码 (Secure Video Path)；系统必须支持方可启用 **L1**，否则拒绝该候选配置。 |

> [!WARNING]
> 很多在线流媒体（如 Amazon Prime、Netflix）在网页端的默认播放策略可能配置为兼容性更高的 L3 候选。不能因为最终走了 L3 就断定底层系统不支持 L1。

### 2. 创建 DRM 对象与 JS 会话

当协商成功后，前端获取 `MediaKeySystemAccess` 实例，并通过以下 API 初始化会话：

1. `access.createMediaKeys()`：异步创建 `MediaKeys`，此步骤在底层 Chromium 中会触发创建 DRM Bridge，**此时安全等级 (L1/L3) 已经被锁定**。
2. `video.setMediaKeys(mediaKeys)`：将 DRM 实例与 `<video>` 媒体标签绑定。
3. `mediaKeys.createSession()`：创建一个空的 `MediaKeySession` 实例。

### 3. 生成请求与内容会话初始化

前端调用 `session.generateRequest(initDataType, initData)`。
* `initData` 通常是从视频流的 PSSH Box 中解析出来的（例如在 `encrypted` 事件中获取）。
* 调用此方法后，Chromium 会通过 JNI 调用 Android 原生的 `MediaDrm.openSession()`，并在原生层真正建立起内容会话，随后调用 `MediaDrm.getKeyRequest()` 生成发往服务器的 Challenge。

### 4. 许可证交换与密钥加载

前端捕获到 `message` 事件后，将 Payload 通过 HTTPS 异步发送给网站的 License Server。
拿到响应后，调用 `session.update(response)` 将 License 交还给 CDM：
* 在 L1 体系下，明文密钥受 TEE (TrustZone) 保护。
* `MediaDrm` 解析 License 结构并将加密的密钥数据安全地传递给底层，普通 Android 环境和 Chromium 绝对无法触碰明文内容密钥。

### 5. 解码与播放输出

密钥加载成功后，播放器开始向 `MediaCodec` 喂入加密的音视频 Sample。
* `MediaDrm` 负责密钥与权限；`MediaCrypto` 负责关联密钥会话。
* 在 L1 (Secure Playback) 时，`MediaCodec` 配置为 `feature-secure-playback = 1`，密文数据直接流入硬件解密引擎与解码器，解码后的像素流直接送入 Display Controller，对 Android OS 完全不可见。

---

## 常见调试与日志排查指南

在针对定制车机浏览器或 WebView 适配流媒体（如 Netflix、Amazon Prime）时，常遇到“明明设备过了 L1，但网页却以 L3 播放”的客诉。

遇到此类问题，不应单纯排查底层 `MediaDrm`，而应结合 Logcat 中的 Chromium 行为进行端到端排查。

### 日志分析示例 (L3 回退案例)

以下为一次典型的流媒体播放 L3 回退日志模式：

```text
// 1. 底层能力探测 (并不代表网页的实际选择)
OEMCrypto_Initialize Level 1 success

// 2. 创建 DRM Bridge 时已经决定使用 L3
Create MediaDrmBridge with level L3 ... for User

// 3. 原生层开启会话
requested_security_level = L3
MediaDrm: openSession() -> sid6
GenerateKeyRequest for sid6

// 4. 许可证交互与状态更新
updateSession(sid6) -> Service certificate loaded, no key added
updateSession(sid6) -> KeysStatusChange(sid6): true

// 5. 解码器创建 (非安全解码器)
Create c2.qti.avc.decoder (feature-secure-playback = 0)
```
**分析结论**：在此类场景中，**L3 在创建 DRM 对象 (`createMediaKeys`) 时就已经被指定**，远早于后续的 License 响应。这说明浏览器或前端页面的协商结果就是 L3，而非底层 License 强行降级。

### 核心排查链路建议

> [!TIP]
> 建议在页面脚本执行前注入 JS 监控代码（如通过 WebView 的 `addDocumentStartJavaScript`），完整抓取 EME API 的入参和返回值，将其与 Logcat 原生日志关联。

| 排查阶段 | 排查要点 | 关键取证 |
| :--- | :--- | :--- |
| **前端策略** | 网站是否因检测到非标准 User-Agent 而主动回退到 L3 策略？ | 抓取网页代码、播放器初始化入参、网络请求响应。 |
| **EME 协商** | 网页是否在候选数组中请求了硬件安全 (`robustness`)？数组的优先级顺序如何？ | `requestMediaKeySystemAccess()` 的完整入参与异常信息。 |
| **浏览器裁决** | Chromium 是否因为某些定制改动，强行过滤了硬件安全候选？ | 拦截 `getConfiguration()` 返回值；增加 `use_hw_secure_codecs` 相关的内核 C++ 打印。 |
| **对象关联** | 前端可能探测了多种配置，最终用哪个实例播放？ | 关联 `createMediaKeys` 结果、`setMediaKeys` 绑定动作与底层 `MediaDrm.openSession()`。 |
