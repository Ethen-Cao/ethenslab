+++
date = '2025-08-08T11:36:11+08:00'
draft = false
title = 'AOSP Camera 快门音播放控制机制'
+++

# AOSP Camera 快门音播放控制机制 (Android 16)

在 Android (AOSP) 框架中，相机快门音（Shutter Sound）的播放受到一套严格的合规机制控制，以满足部分地区防偷拍的法律要求。其核心设计思想是将**播放请求**与**合规裁决**分离：相机服务层（Native）无条件发起强制播放请求，而音频服务层（Java）结合系统属性、全局配置和动态网络（SIM 卡）环境进行最终裁决与音量路由。

本文档基于 Android 16 源码，详述了快门音从资源加载、策略评估到底层硬件输出的完整生命周期。

## 1. 资源加载与客制化替换 (CameraService)

相机提示音文件硬编码在底层原生服务中，而非由上层 App 传递。资源加载遵循按需加载（Lazy Loading）和双分区回退（Fallback）机制。

**核心代码路径**：`frameworks/av/services/camera/libcameraservice/CameraService.cpp`

```cpp
// CameraService::loadSoundLocked()
mSoundPlayer[SOUND_SHUTTER] = newMediaPlayer("/product/media/audio/ui/camera_click.ogg");
if (mSoundPlayer[SOUND_SHUTTER] == nullptr) {
    mSoundPlayer[SOUND_SHUTTER] = newMediaPlayer("/system/media/audio/ui/camera_click.ogg");
}
```

> [!TIP]
> **无侵入替换方案**：得益于双分区机制，定制开发时无需修改框架源码。只需在 `device.mk` 中通过 `PRODUCT_COPY_FILES` 将自定义音频文件拷贝至 `product` 分区目录（`/product/media/audio/ui/camera_click.ogg`），即可实现拦截覆盖。

## 2. 动态合规裁决 (AudioService)

`AudioService.java` 是快门音策略的核心枢纽。系统会在初始化阶段以及配置发生变更（如插拔 SIM 卡、网络切换）时，动态评估当前是否必须强制发声。

**核心代码路径**：`frameworks/base/services/core/java/com/android/server/audio/AudioService.java`

触发逻辑 `readCameraSoundForced()` 会依次评估以下条件（满足其一即视为强制发声）：
1. 系统底层属性 `audio.camerasound.force` 设为 `true`。
2. 框架层全局资源 `config_camera_sound_forced` 设为 `true`。
3. 当前活跃的任意 SIM 卡所在区域配置（基于 MCC/MNC）要求强制发声。

### 音量与路由策略
* **强制发声生效**：AudioService 会将 `STREAM_SYSTEM_ENFORCED` 类型的音频流移出受静音模式控制的列表，将其音量固定为最大，并通知 `AudioPolicyManager` 强行路由至外放扬声器。
* **允许静音（未强制）**：该流类型会被保留在受控列表中。当设备处于静音或震动模式时，该流类型的实际下发音量 (Volume Index) 会被直接置为 0。

## 3. 底层防静音拦截 (AudioFlinger)

相机的播放请求带有特殊的流类型标签 `AUDIO_STREAM_ENFORCED_AUDIBLE`。当底层音频引擎识别到该标签时，会严格拒绝执行应用层的物理 Mute 请求。

**核心代码路径**：`frameworks/av/services/audioflinger/Tracks.cpp`

```cpp
// OpPlayAudio 检查拦截
if (streamType == AUDIO_STREAM_ENFORCED_AUDIBLE) {
    ALOGD("OpPlayAudio: not muting track:%d usage:%d ENFORCED_AUDIBLE", id, attr.usage);
    return nullptr; // 拒绝执行 Mute
}
```

**实现静默的最终原理**：
既然底层无法被 Mute，如果当前允许静音，声音是如何消失的？
答案在于混音计算。当设备允许静音且开启静音模式时，AudioService 下发的实际音量系数为 `0`。AudioFlinger 即使强制输出数据，由于 PCM 数据乘以系数 `0`，最终物理扬声器播放出的仍是无声音频数据。

## 4. UI 界面状态获取 (Camera App)

系统是否允许关闭快门音，最终会决定 Camera App 是否在设置界面展示“关闭快门音”开关。上层 App 通过 `Camera.getCameraInfo()` 经过 JNI 获取底层只读属性。

**核心代码路径**：`frameworks/base/core/jni/android_hardware_Camera.cpp`

```cpp
property_get("ro.camera.sound.forced", value, "0");
jboolean canDisableShutterSound = (strncmp(value, "0", 2) == 0);
```

> [!WARNING]
> AOSP 的 JNI 层实现存在一定的局限性：它仅读取了静态系统属性 `ro.camera.sound.forced`，并未结合 AudioService 中的 SIM 卡动态状态。这要求在进行定制开发时，必须确保上层 UI 获取策略与底层的音频路由策略保持严格同步。

## 完整交互时序图

以下展示了快门音从配置检查到最终输出的完整跨层级时序调用流程。

```plantuml
@startuml
!theme plain
skinparam componentStyle material
skinparam defaultFontColor black
skinparam sequenceParticipantFontColor black
skinparam sequenceActorFontColor black
autonumber "<b>[0]"

actor "User" as User
participant "Camera App" as App

box "Java Framework" #LightCyan
participant "Camera.java (JNI)" as JNI
participant "AudioService" as AS
participant "SubscriptionManager" as SubMgr
end box

box "Native Framework (C++)" #LightYellow
participant "CameraService" as CS
participant "AudioPolicyManager" as APM
participant "AudioFlinger" as AF
end box

participant "Speaker" as SPK

== 初始化与动态配置评估 ==

-> AS: onConfigurationChanged()
activate AS
AS -> AS: readCameraSoundForced()
activate AS

AS -> SubMgr: getActiveSubscriptionIdList()
SubMgr --> AS: return 活跃 SIM 卡列表
AS --> AS: 根据系统属性与 SIM 状态进行综合裁决
de务 deactivate AS

alt cameraSoundForced == true (强制发声)
    AS -> AS: 移出静音管控列表并最大化音量
    AS -> APM: MSG_SET_FORCE_USE (FORCE_SYSTEM_ENFORCED)
else cameraSoundForced == false (允许静音)
    AS -> AS: 加入静音管控列表
    AS -> APM: MSG_SET_FORCE_USE (FORCE_NONE)
end
deactivate AS

== UI 状态获取 ==

User -> App: 打开相机设置
App -> JNI: getCameraInfo()
JNI -> JNI: property_get("ro.camera.sound.forced")
JNI --> App: 返回 canDisableShutterSound 状态

== 快门触发与硬件输出 ==

User -> App: 点击快门
App -> CS: Capture Request
CS -> CS: playSound(SOUND_SHUTTER)\n强制设为 AUDIO_STREAM_ENFORCED_AUDIBLE

CS -> AF: createTrack & start()
AF -> APM: 请求路由策略与当前音量
APM --> AF: 返回 Output 句柄和 Volume

AF -> AF: Tracks.cpp 豁免 Mute 检查\n(发现 ENFORCED_AUDIBLE 流)

alt Volume == 0 (允许静音且当前为静音模式)
    AF -> SPK: 传输振幅为 0 的静默 PCM 数据
else Volume > 0 (强制发声或正常音量模式)
    AF -> SPK: 传输实际音频波形数据
end

@enduml
```
