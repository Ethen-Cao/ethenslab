---
title: "AAOS Audio设计原理与应用"
description: "基于 Android 17 AOSP 的 24 篇车载音频系列，从架构、路由和焦点到 HAL、录音、多音区与故障定位。"
date: 2026-10-23T12:00:00+08:00
weight: 20
tags: ["Android", "AAOS", "Audio", "Android 17"]
ShowToc: true
TocOpen: true
draft: false
isCJKLanguage: true
layout: single
---

驾驶员听音乐，导航开始播报，后排乘客仍在看视频；随后手机来电，通话结束后音乐又恢复。这些体验依赖的不是一个“车载音频开关”，而是声音语义、焦点仲裁、音区路由、音量状态、音频数据传输与设备控制的协作。

本系列面向系统与座舱开发者，以 Android 17 AOSP 的具体实现解释这些机制。阅读目标是能够沿着“场景意图 → 策略决定 → 数据通路 → 设备状态”追踪一次声音变化，知道应修改哪一层、通过什么证据验证，而不是仅记住几个类名或配置字段。

## 阅读路线

第一次系统学习，按 01—24 的顺序阅读：先建立模型，再理解策略和声音控制，随后进入 HAL、数据链路与车载场景，最后做集成和故障定位。

已有 Android 音频基础的工程师，可以从 04—07 补齐车载语义与多音区，再读 08—14 的焦点、音量与厂商接口。负责应用接入时，优先阅读 03、08、09、17；负责车机集成时，优先阅读 02、05—07、11—14、22—24。遇到“有播放状态但没有声音”，先读 24 的分层诊断，再回到对应机制。

## 完整目录

### 基础模型与路由

| 文章 | 主要问题 |
|---|---|
| [01 总体架构与设计目标]({{< relref "01-architecture.md" >}}) | 应用、服务进程、策略、HAL 各自解决什么问题，控制调用与音频数据在哪里分开。 |
| [02 启动流程与配置体系]({{< relref "02-startup-and-configuration.md" >}}) | 配置从哪里来，何时建立音区和策略，初始化成功为何不等于所有硬件能力可用。 |
| [03 应用如何接入车载音频]({{< relref "03-application-contracts.md" >}}) | 普通媒体应用和系统控制应用使用哪些接口，怎样管理播放意图、焦点和生命周期。 |
| [04 声音的语义模型]({{< relref "04-audio-attributes-and-contexts.md" >}}) | usage、content type、context 与 Product Strategy 如何表达不同层次的语义。 |
| [05 多音区与多用户]({{< relref "05-zones-users-and-occupants.md" >}}) | 座位、乘员、用户、UID、音区与设备如何关联，为什么编号不能混用。 |
| [06 动态音频路由]({{< relref "06-dynamic-routing.md" >}}) | AudioMix、匹配规则与 affinity 如何让同样的音乐用途进入不同音区。 |
| [07 Core Audio 路由与音量方案]({{< relref "07-core-audio-routing-and-volume.md" >}}) | CAP 如何参与车载集成，两套配置模型怎样保持一致。 |

### 焦点与声音控制

| 文章 | 主要问题 |
|---|---|
| [08 音频焦点仲裁]({{< relref "08-audio-focus.md" >}}) | 独占、并发、拒绝、延迟和恢复怎样在一个音区内协作。 |
| [09 压低音量与淡入淡出]({{< relref "09-ducking-and-fading.md" >}}) | 音乐切换时谁淡出，导航如何压低音乐，新赢家为什么不一定自动淡入。 |
| [10 音频焦点强制执行]({{< relref "10-focus-enforcement.md" >}}) | 如何约束不遵守焦点的播放，以及适用音区、车辆状态和属性匹配条件。 |
| [11 音量组与音量键]({{< relref "11-volume-groups-and-keys.md" >}}) | 按键怎样选组，音量索引如何落到设备增益或 Core volume，UI 如何同步。 |
| [12 静音、增益限制与激活音量]({{< relref "12-muting-gain-and-activation.md" >}}) | 用户请求为何会被硬件限制覆盖，静音和衰减为什么不能视为同一种状态。 |
| [13 OEM 音频策略扩展]({{< relref "13-oem-audio-policies.md" >}}) | 厂商如何通过受约束的接口影响焦点、ducking 和音量决策。 |
| [14 AudioControl HAL 的设计与应用]({{< relref "14-audio-control-hal.md" >}}) | 汽车控制接口如何传递焦点、duck、mute、gain 和设备配置。 |

### 播放录音与外部音源

| 文章 | 主要问题 |
|---|---|
| [15 从 AudioTrack 到扬声器]({{< relref "15-playback-pipeline-and-audio-hal.md" >}}) | 轨道、输出、缓冲、线程及 Audio HAL 的 port、patch、stream 如何连接。 |
| [16 混音、低延迟、Offload 与音效]({{< relref "16-performance-and-effects.md" >}}) | 不同处理路径怎样被选中，如何理解延迟、功耗、格式与音效的取舍。 |
| [17 录音链路与麦克风隐私]({{< relref "17-capture-and-privacy.md" >}}) | 录音为什么可能启动成功却读到静音，权限、输入路由和并发如何共同裁决。 |
| [18 语音交互与唤醒音频]({{< relref "18-voice-and-hotword.md" >}}) | 热词检测、语音识别、录音与预处理如何协作，DSP 能力的边界在哪里。 |
| [19 蓝牙音乐与通话]({{< relref "19-bluetooth-and-calls.md" >}}) | 车机的 Sink、Client 角色如何影响手机音乐、来电、通话和恢复。 |
| [20 外部音源与 AudioPatch]({{< relref "20-external-audio-sources.md" >}}) | 外部源、硬件 patch 和 HwAudioSource 怎样参与 Android 可见的音频状态。 |

### 多音区扩展与系统集成

| 文章 | 主要问题 |
|---|---|
| [21 媒体共享与音区镜像]({{< relref "21-media-sharing-and-mirroring.md" >}}) | 共享到主音区和多个音区镜像有什么不同，怎样处理请求、冲突与恢复。 |
| [22 动态设备与音区配置切换]({{< relref "22-dynamic-devices-and-zone-configs.md" >}}) | 插拔和配置变化怎样影响可用设备、路由、焦点与音量控制。 |
| [23 电源策略与服务恢复]({{< relref "23-power-and-recovery.md" >}}) | AUDIO power policy、休眠唤醒、服务死亡及重新初始化怎样影响声音。 |
| [24 系统集成与故障定位实战]({{< relref "24-debugging-and-integration.md" >}}) | 怎样把跨层证据关联起来，定位无声、错路由、音量异常与恢复失败。 |

## 理解全系列需要分清的概念

| 概念 | 主要回答的问题 | 不能直接替代什么 |
|---|---|---|
| AudioAttributes | 这一路播放或采集具有怎样的用途和内容语义 | 物理扬声器编号或用户编号 |
| CarAudioContext | 车载策略怎样归类一组声音用途 | 唯一音轨或音区 |
| Audio zone | 哪个空间范围具有独立的音频策略和输出配置 | Android user 或座位 ID |
| Occupant zone | 哪组座位、显示与外设面向某位乘员 | 一条音频输出流 |
| Audio focus | 多个请求在当前规则下怎样并发、失去和恢复焦点 | 音轨是否真实输出样本 |
| Routing | 播放或输入被选择到什么设备与路径 | 授予焦点或解除静音 |
| Volume group | 哪些设备或用途按一个控制量调整音量 | 一个 App 的播放器音量 |
| Ducking | 为并发场景降低其他声音的响度 | 永久失焦后的淡出 |
| Fade-in / fade-out | 播放器增益随时间改变 | 前后扬声器的声场平衡 |
| Audio HAL | Android 音频流、端口、连接与设备能力契约 | 汽车 AudioControl HAL |
| AudioControl HAL | 汽车音频控制和状态回报契约 | PCM 样本的必经通道 |
| Capture silencing | 活动录音客户端是否获得真实样本 | 播放侧的失焦通知 |

同一个表面现象可能由不同机制导致。例如，音量索引没有变化但声音变小，可能是 duck、HAL attenuation 或另一层处理；拿到焦点但无声，也可能是路由、静音、供数或硬件状态的问题。文章中的例子会保留这些层次，避免用一个状态推断整条链路。

## 源码基线

系列使用的 manifest 默认 revision 是 `android17-release`。AOSP 是多个 Git 项目组成的源码树，下表分别固定主要项目的提交；正文引用采用对应提交下的文件与行号。将本系列用于另一款产品时，应同时比较源码提交、资源覆盖、aconfig 状态和 HAL 能力，不能只比较 Android 大版本名称。

| 项目 | 固定提交 |
|---|---|
| `frameworks/base` | [`94b4c163b7dfe5ce3607f7bb8456f9573f7de57d`](https://android.googlesource.com/platform/frameworks/base/+/94b4c163b7dfe5ce3607f7bb8456f9573f7de57d) |
| `frameworks/av` | [`475269ec44acec82792be6b01fb8e16357d4d2c8`](https://android.googlesource.com/platform/frameworks/av/+/475269ec44acec82792be6b01fb8e16357d4d2c8) |
| `packages/services/Car` | [`9f04df65daa8b9a65ee05fd4039fe95446874d76`](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76) |
| `hardware/interfaces` | [`0162af698935100a590b7359581ac8b1b80693e5`](https://android.googlesource.com/platform/hardware/interfaces/+/0162af698935100a590b7359581ac8b1b80693e5) |
| `packages/modules/Bluetooth` | [`c77db469de80f86660bc053bec4dee0c5d4b947c`](https://android.googlesource.com/platform/packages/modules/Bluetooth/+/c77db469de80f86660bc053bec4dee0c5d4b947c) |
| `device/generic/car` | [`f7883270a86b40fb7c3f11f2f755af4a43d0beef`](https://android.googlesource.com/platform/device/generic/car/+/f7883270a86b40fb7c3f11f2f755af4a43d0beef) |
| `build/release` | [`c85f4aebe46714235599a9bd6430a0fe30c6e8d5`](https://android.googlesource.com/platform/build/release/+/c85f4aebe46714235599a9bd6430a0fe30c6e8d5) |
| manifest | [`ad156f32caaa06dae91c02d443f6a8fe210eaa54`](https://android.googlesource.com/platform/manifest/+/ad156f32caaa06dae91c02d443f6a8fe210eaa54) |

正文的“默认值”总是限定在相应实现或配置中。基础资源、模拟器 overlay、厂商产品配置和运行时状态并非同一层。例如，基础资源关闭某项能力，不妨碍模拟器或产品通过覆盖启用。源码存在某个分支，也不能独立证明它是 Android 17 首次引入的功能。

## 图与源码的阅读方法

架构图采用统一的软件架构模型和独立 HTML，英文名称与源码实体对应，图外提供中文解释。框架 API 是技术角色，服务进程是运行边界；容器的包含关系不代表函数调用。蓝色线表达控制关系，绿色线表达音频样本数据，配置关系单独标识。总体架构图位于第 01 篇，路由、音量、HAL、播放与录音的补充视图分别位于第 06、11、14、15、17 篇。

架构图以独立 HTML 提供，也保留可编辑模型，便于跟随产品配置演进。下列视图与正文采用同一源码基线。

| 视图 | 独立图页 | 源模型 |
|---|---|---|
| 总体架构 | [打开 HTML](../../diagrams/aaos17-audio-overview.html) | [下载模型](models/aaos17-audio-overview.diagram.json) |
| 动态路由 | [打开 HTML](../../diagrams/aaos17-audio-routing.html) | [下载模型](models/aaos17-audio-routing.diagram.json) |
| 音量路径 | [打开 HTML](../../diagrams/aaos17-audio-volume.html) | [下载模型](models/aaos17-audio-volume.diagram.json) |
| 两类 HAL 契约 | [打开 HTML](../../diagrams/aaos17-audio-hal-contracts.html) | [下载模型](models/aaos17-audio-hal-contracts.diagram.json) |
| 播放数据路径 | [打开 HTML](../../diagrams/aaos17-audio-playback.html) | [下载模型](models/aaos17-audio-playback.diagram.json) |
| 录音与静音控制 | [打开 HTML](../../diagrams/aaos17-audio-capture.html) | [下载模型](models/aaos17-audio-capture.diagram.json) |

时序图使用 Mermaid，表达选定场景的先后关系。为了让主线可读，图中会省略部分封装、线程投递或辅助调用；图旁说明其范围，正文和固定源码链接用于展开具体实现。不能从简化时序推断每个箭头都跨进程，也不能从调用关系推断 PCM 一定沿相同路径流动。

文章中的配置和代码分为源码摘录、最小示例与教学伪代码。示例用于解释接口和约束，涉及系统权限、功能开关或特定 HAL 的部分会给出前置条件。实验步骤中的观察点表示应该采集什么证据，不表示某款设备已经得到相应结果。

## 从功能实现走向集成验证

集成时建议为音乐、导航、通话、语音输入及后排媒体分别建立一条可追踪用例，记录属性、用户、UID、音区、设备、焦点结果和有效音量状态。先验证单一场景，再组合播放、用户切换、插拔与服务恢复；每次只改变一个决定性条件，才能把异常定位到配置、策略、数据或硬件边界。

调试命令需要对应设备权限和构建类型。静态源码分析能说明条件和分支，服务 dump 能说明当时的软件状态，最终可闻输出、声学延迟和回声处理质量则需要相应硬件与测量。第 24 篇将这些证据组织为一条排障路径，前面的各篇提供每一层的解释基础。

## 现有测试源码索引

下表选取与 01–24 篇主题相关的现有测试入口，链接固定到本系列使用的源码提交。表中条件根据测试体中的 `assert`、`expect` 或 `verify` 核对；本次仅阅读测试源码，没有执行这些测试，也不表示这些代表用例覆盖了对应章节的全部功能。测试构造的配置、feature flag 和 mock 状态应与断言一起阅读。

| 文章 | 现有测试文件与入口 | 适合核对的条件 |
|---|---|---|
| 01–02 总体架构、启动与配置 | [CarAudioServiceUnitTest.java:986](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarAudioServiceUnitTest.java#986)（`init_withVolumeControlPolicyRegistrationError_fails_asyncInit`）<br>[CarAudioZonesHelperImplUnitTest.java:294](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarAudioZonesHelperImplUnitTest.java#294)（`loadAudioZones_parsesAllZones`） | 音量策略注册失败时，异步初始化等待返回 false；给定 XML 样例解析出的 zone 数量符合预期。用于连接初始化与配置模型，不代表整套架构已被单测验证。 |
| 03–04 应用契约、属性与 Context | [CarAudioContextTest.java:185](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarAudioContextTest.java#185)（`getContextForAudioAttributes_forAttributeWithValidUsage_returnsContext`）<br>[CarAudioFocusUnitTest.java:325](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarAudioFocusUnitTest.java#325)（`onAudioFocusRequest_withSameClientIdDifferentUsage_requestFailed`） | MEDIA 属性映射到测试媒体 context；已有媒体请求复用同一 client id 改申请导航用途时返回 FAILED。 |
| 05–06 音区用户、动态路由 | [CarAudioServiceUnitTest.java:2516](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarAudioServiceUnitTest.java#2516)（`onOccupantZoneConfigChanged_userAssignedToPrimaryZone`）<br>[CarAudioDynamicRoutingTest.java:80](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarAudioDynamicRoutingTest.java#80)（`setupAudioDynamicRouting`） | occupant 用户变更后更新音区用户映射；生成的媒体 AudioMix 指向预期 bus，并匹配 MEDIA/GAME/UNKNOWN，而不匹配导航、通话等其他用途。 |
| 07 核心音频路由与音量 | [CoreAudioHelperTest.java:114](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CoreAudioHelperTest.java#114)（`getStrategyForAudioAttributes_withInvalidAttributes_returnsInvalidStrategy`）<br>[CoreAudioHelperTest.java:135](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CoreAudioHelperTest.java#135)（`getStrategyForAudioAttributesOrDefault_withInvalidAttributes_fallbacksOnDefault`） | 不支持的属性在严格查询中返回 INVALID_STRATEGY，在允许默认策略的查询中回退到样例默认策略；两种入口不可混为一谈。 |
| 08 音频焦点 | [CarAudioFocusUnitTest.java:470](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarAudioFocusUnitTest.java#470)（`onAudioFocusRequest_exclusiveRequest_holderLosesFocus`）<br>[CarAudioFocusUnitTest.java:917](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarAudioFocusUnitTest.java#917)（`onAudioFocus_forRequestDelayed_delayedFocusGained`） | 独占永久请求使原持有者收到 LOSS；可延迟请求先得到 DELAYED，通话放弃焦点后收到 GAIN。断言针对回调结果，不测声学切换时长。 |
| 09 Ducking 与淡入淡出 | [FadeOutManagerTest.java:135](https://android.googlesource.com/platform/frameworks/base/+/94b4c163b7dfe5ce3607f7bb8456f9573f7de57d/services/tests/audio/src/com/android/server/audio/FadeOutManagerTest.java#135)（`testCanBeFadedOut_forUnFadableConfig_returnsFalse`）<br>[FadeOutManagerTest.java:164](https://android.googlesource.com/platform/frameworks/base/+/94b4c163b7dfe5ce3607f7bb8456f9573f7de57d/services/tests/audio/src/com/android/server/audio/FadeOutManagerTest.java#164)（`testUnfadeOutUid_getsUnfaded_isFadedReturnsFalse`） | 测试配置中的 speech 播放和 AAudio 类型不满足淡出资格；恢复一个 UID 后，该 UID 的淡出状态清除，另一 UID 保持。这里没有证明新赢家自动淡入或两路严格串行。 |
| 10 焦点强制执行 | [CarAudioFocusEnforcementUnitTest.java:428](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarAudioFocusEnforcementUnitTest.java#428)（`onAudioPlaybackChange_withFocusHolderAndMismatchedTags_silences`）<br>[CarAudioFocusEnforcementUnitTest.java:714](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarAudioFocusEnforcementUnitTest.java#714)（`onAudioPlaybackChange_forNonPrimaryZone_doesNotSilence`） | UID 与媒体用途相同但 tags 不匹配时，代理音量被置为 0；非主区播放回调不触发该执行器的音量设置。 |
| 11–12 音量组、静音与激活 | [CarAudioVolumeGroupTest.java:203](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarAudioVolumeGroupTest.java#203)（`setCurrentGainIndex_updatesCurrentGainIndex`）<br>[CarVolumeGroupUnitTest.java:227](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarVolumeGroupUnitTest.java#227)（`setMuted_whenHalMuted_onDeactivation_returnsFalse`）<br>[CarVolumeGroupUnitTest.java:523](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarVolumeGroupUnitTest.java#523)（`handleActivationVolume_withVolumeBelowMinActivationVolume`） | 设置索引写入带用户、zone、配置与组身份的设置项；HAL 静音时取消静音返回 false；允许的激活触发把低于最小激活值的索引调整到下界。相邻测试覆盖高于上界及范围内不变。 |
| 13–14 OEM 策略、AudioControl HAL | [CarOemAudioVolumeProxyServiceTest.java:77](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/oem/CarOemAudioVolumeProxyServiceTest.java#77)（`getSuggestedGroupForVolumeChange`）<br>[HalAudioFocusTest.java:116](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/HalAudioFocusTest.java#116)（`registerFocusListener_succeeds`） | OEM 音量代理返回样例服务给出的组变化对象；HAL 焦点监听注册交给 AudioControlWrapper。前者是正常返回路径，不能据此宣称已验证超时故障恢复。 |
| 15–16 播放管线、性能路径与音效 | [audiotrack_tests.cpp:320](https://android.googlesource.com/platform/frameworks/av/+/475269ec44acec82792be6b01fb8e16357d4d2c8/media/libaudioclient/tests/audiotrack_tests.cpp#320)（`AudioTrackCreateTest.TestCreateTrack`） | 参数化轨道创建核对格式、声道数、采样率及适用的 session，并检查 start 与数据处理返回值；参数包含 FAST、DEEP_BUFFER 等请求，不等于断言最终接受 FAST，也不是延迟或音效质量测量。 |
| 17–18 录音与语音唤醒 | [SoundTriggerHalConcurrentCaptureHandlerTest.java:60](https://android.googlesource.com/platform/frameworks/base/+/94b4c163b7dfe5ce3607f7bb8456f9573f7de57d/services/tests/voiceinteractiontests/src/com/android/server/soundtrigger_middleware/SoundTriggerHalConcurrentCaptureHandlerTest.java#60)（`testBasic`） | 已有 recognition 遇到并发采集 active 后调用 stopRecognition，回报 ABORTED 且 recognitionStillActive=false；采集结束后通知资源可用。该入口聚焦并发采集与 SoundTrigger 协调。 |
| 19–20 蓝牙与外部音源 | [A2dpSinkStreamHandlerTest.java:269](https://android.googlesource.com/platform/packages/modules/Bluetooth/+/c77db469de80f86660bc053bec4dee0c5d4b947c/android/app/tests/unit/src/com/android/bluetooth/a2dpsink/A2dpSinkStreamHandlerTest.java#269)（`testFocusLostTransient`）<br>[HalAudioFocusTest.java:188](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/HalAudioFocusTest.java#188)（`requestAudioFocus_withFocusRequestDelayed`） | A2DP Sink 临时失焦时将 native gain 置 0，并不调用 abandon；外部 HAL 焦点请求得到 DELAYED 时，桥接层向 HAL 回报 LOSS。这里只核对控制状态，不验证车辆实际发声。 |
| 21–22 镜像、共享与动态设备 | [CarAudioMirrorRequestHandlerTest.java:102](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarAudioMirrorRequestHandlerTest.java#102)（`getUniqueRequestIdAndAssignMirrorDevice_forOutOfAvailableDevices`）<br>[CarAudioDeviceCallbackTest.java:65](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarAudioDeviceCallbackTest.java#65)（`onAudioDevicesRemoved`） | 样例镜像设备池耗尽后继续申请返回 INVALID_REQUEST_ID；设备移除回调向 CarAudioService 转交预期设备集合。转发断言本身不证明自动配置回退或完整媒体共享流程。 |
| 23–24 电源恢复与集成排障 | [CarAudioServiceUnitTest.java:2955](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarAudioServiceUnitTest.java#2955)（`onAudioServerUp_forCarAudioServiceCallback`）<br>[CarAudioServiceUnitTest.java:3063](https://android.googlesource.com/platform/packages/services/Car/+/9f04df65daa8b9a65ee05fd4039fe95446874d76/tests/CarServiceUnitTest/src/com/android/car/audio/CarAudioServiceUnitTest.java#3063)（`onAudioServerUp_forUserIdAssignments`） | audioserver down/up 后重新注册策略及相关回调，并恢复样例中的五个音区与用户映射；适合作为恢复状态检查入口，不等同于车辆休眠唤醒及全链路声学验收。 |

这些入口适合用于阅读源码、选择回归用例和设计产品验收。依赖真实音频服务、素材或设备的 native 测试，还需要按对应测试模块准备运行环境；通过 mock 的状态断言不能替代扬声器输出、衰减曲线或整车时延测量。
