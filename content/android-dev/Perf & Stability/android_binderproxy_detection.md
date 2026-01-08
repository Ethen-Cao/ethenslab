+++
date = '2025-09-29T11:36:11+08:00'
draft = false
title = 'Android Binder Proxy 限制机制'
+++

![](/ethenslab/images/binderproxy.drawio.png)
本图描述了 Android 系统中 **Binder Proxy 数量限制（BinderProxy Limit）** 的实现流程，涉及 `ActivityManagerService`、`BinderInternal`、JNI 层、`BpBinder` 等关键组件。

---

## 1. 关键模块

### 1.1 Java 层

* **ActivityManagerService (AMS)**
  系统服务的核心，负责启用 Binder Proxy 限制，并设置回调。

* **BinderInternal**
  桥接 AMS 与 Native 层的接口类，提供

  * `nSetBinderProxyCountEnabled`
  * `setBinderProxyCountCallback`
    等方法。

* **BinderProxyLimitListener / Delegate**
  当达到 Binder Proxy 数量上限时被触发，执行对应的回调逻辑。

---

### 1.2 Native 层 (JNI)

* **libandroid_runtime**
  JNI 桥接库，实现了 `android_os_BinderInternal_setBinderProxyCountEnabled` 与回调代理 `android_os_BinderInternal_proxyLimitcallback`。

* **libbinder**
  Binder 内核通信库，负责 Binder 代理对象的创建与管理。
  其中 `BpBinder::create` 在生成 Binder 代理对象时进行计数与节流。

---

## 2. 调用流程

1. **AMS 启动限制**

   * `ActivityManagerService` 调用
     `BinderInternal.nSetBinderProxyCountEnabled(true)`
     以启用 Binder Proxy 限制。

2. **设置回调**

   * AMS 通过 `BinderInternal.setBinderProxyCountCallback(listener)` 注册回调。
   * 回调实现由 `BinderProxyLimitListenerDelegate` 代理。

3. **JNI 层交互**

   * Java 调用会映射到 JNI：
     `android_os_BinderInternal_setBinderProxyCountEnabled`。
   * Native 创建回调代理：
     `android_os_BinderInternal_proxyLimitcallback`。

4. **Native 层计数逻辑**

   * `BpBinder::create` 在生成新 Binder Proxy 时增加计数。
   * 若达到阈值，触发回调 `binderProxyLimitCallbackFromNative`。

5. **Java 层通知**

   * 回调委派给 `BinderProxyLimitListenerDelegate`，最终执行
     `BinderProxyLimitListener.onLimitReached(uid)`。
   * `ActivityManagerService` 根据 UID 采取措施：

     * 如果是 `SYSTEM_UID` → 跳过杀进程。
     * 否则 → 调用 `killUid()` 并触发 `VMRuntime.requestConcurrentGC()` 进行清理。

---

## 3. 保护机制说明

* **目的**：防止单个应用创建过多 Binder 代理对象，导致系统内存或 Binder 资源耗尽。
* **实现方式**：

  * Native 层计数 (`BpBinder::create`)。
  * 超限回调 → Java 层处理。
* **系统稳定性**：避免因恶意或错误应用引发全局崩溃。

---

## 4. 关键点总结

* Java 层通过 **BinderInternal** 开启和注册回调。
* JNI 层桥接 Java 与 Native。
* Native 层 (`libbinder`) 负责实际的 Binder Proxy 创建与计数。
* 触发阈值时 → 调用回调 → AMS 决策处理（杀进程或回收）。

---

