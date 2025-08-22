+++
date = '2025-08-08T11:36:11+08:00'
draft = false
title = '使用AndroidStudio调试AOSP'
+++

## 调试Java进程

本文介绍如何在 Android Studio 中调试 AOSP (Android Open Source Project) 进程，尤其是像 system_server 这样的系统进程。调试 AOSP 与普通应用调试有所不同，需要借助 JDWP 协议和 adb 端口转发。

### 前置条件

环境准备：

* 一台可以刷入 AOSP 的设备或模拟器
* 已编译好的 AOSP（推荐 userdebug 或 eng 构建）
* PC 上安装 Android Studio（最新版）

权限要求：

* 设备必须支持 adb root
* 设备需要打开调试属性，例如：
    ```shell
    adb root
    adb shell setprop persist.system_server.debuggable 1
    adb shell stop
    adb shell start
    ```
    上述命令让 system_server 在启动时支持调试。

### 调试原理

Android 使用 JDWP (Java Debug Wire Protocol) 进行 Java 进程调试：

* system_server 内部：包含一个 JDWP Listener 线程，负责接收调试命令并执行（挂起线程、返回堆栈、单步执行等）。
* adb：提供 adb forward 功能，将 PC 本地端口与设备进程的 JDWP 通道连接起来。
* Android Studio：作为调试器，通过 JDWP 协议与 system_server 通信。

数据流示意：
```txt
[Android Studio Debugger]
        |
        | JDWP 命令 (localhost:8700)
        v
[adb forward tcp:8700 jdwp:<PID>]
        |
        v
[system_server JDWP Listener 线程]
        |
        | 执行调试操作
        v
[调试响应返回到 IDE]
```

原理图：

![](/ethenslab/images/android-jdwp.png)

操作步骤
1. 确认 system_server 进程
    ```shell
    adb shell ps -A | grep system_server
    ```
    记下 system_server 的 PID，例如 1234。

2. 查看可调试进程
    ```shell
    adb jdwp
    ```
    输出的列表包含所有支持 JDWP 的进程 PID，确认其中有 system_server 的 PID。

3. 建立端口转发
    ```shell
    adb forward tcp:8700 jdwp:1234
    ```
    此命令会将 PC 本地的 localhost:8700 绑定到 system_server 的 JDWP 通道。

4. 在 Android Studio Attach

    打开 Run → Attach debugger to Android process。
    如果列表中显示了 system_server，直接选择。

    如果未显示，可以手动配置：
    Run → Edit Configurations → Remote JVM Debug

    地址填写 localhost，端口填写 8700

    点击 OK 并启动调试。

5. 进行调试

    可以在 framework 层源码中打断点，例如 ActivityManagerService.java。
    IDE 会在对应断点暂停，允许查看堆栈、变量、线程等信息。


## 调试Native进程

1. 将 lldb-server 推送到设备：

    ```shell
    adb push prebuilts/clang/host/linux-x86/clang-r450784e/runtimes_ndk_cxx/aarch64/lldb-server /data/local/tmp/
    adb shell chmod +x /data/local/tmp/lldb-server
    ```

2. 在设备上启动 lldb-server 并附加到目标进程
    1. 获取目标进程 PID
        ```shell
        adb shell ps -A | grep cameraserver
        ```
        假设 PID = 2345。
    2. 启动 lldb-server，以 gdbserver 模式附加：
        ```shell
        adb shell /data/local/tmp/lldb-server gdbserver *:5039 --attach 2345
        ```
        ⚠️ 注意：此时进程会被挂起，直到 IDE 连接
3. 建立端口转发
    ```shell
    adb forward tcp:5039 tcp:5039
    ```
4. 在 Android Studio 配置调试
    1. 打开 Run → Edit Configurations...
    2. 点击 + → 选择 C/C++ Remote Debug
    3. 配置关键参数：
        * Name：例如 Debug CameraServer
        * Executable：本地符号文件路径，例如 out/target/product/<device>/symbols/system/bin/cameraserver
        * Debugger：本地 lldb 可执行文件，例如prebuilts/clang/host/linux-x86/lldb/bin/lldb
        * Target Remote：localhost:5039
5. 开始调试
    * 在源码中设置断点。
    * 点击调试按钮（绿色小虫子）。
    * Android Studio 会连接到设备上的 lldb-server，附加进程并在断点处停下。

### 原理图

![](/ethenslab/static/images/androidstduio-native-debugger.png)