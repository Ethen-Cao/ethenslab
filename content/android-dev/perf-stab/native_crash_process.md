---
title: "Android Native Crash 处理机制深度解析"
date: 2024-07-29T10:00:00+08:00 
draft: false
---

在 Android 系统中，Native Crash 的处理是一个高度解耦且极其鲁棒的多进程协作闭环。其核心哲学是：**在损坏的现场外（Out-of-Process）进行安全重建**。

## 1. 系统组件架构 (Architectural Overview)

下图展示了参与 Crash 处理的关键组件及其静态拓扑关系：

```mermaid
graph LR
    subgraph "Native Process (Crasher)"
        SC[libsigchain.so]
        DH[libdebuggerd_handler.so]
        PT[Pseudothread]
        VM[VM Process / Snapshot]
    end

    subgraph "Debuggerd Daemon System"
        CD[crash_dump64/32]
        T[tombstoned]
    end

    subgraph "System Services"
        LOG[logd / kmsg]
        AMS[ActivityManagerService]
    end

    DH -- "linker_debuggerd_init" --> L[Linker]
    SC -- "special_handler" --> DH
    DH -- "clone(no CLONE_FILES)" --> PT
    PT -- "exec" --> CD
    CD -- "ptrace(SEIZE/INTERRUPT)" --> Crasher
    PT -- "double-fork" --> VM
    CD -- "ptrace(read memory)" --> VM
    CD -- "kDumpRequest" --> T
    T -- "InterceptCheck" --> CD
    CD -- "ndebugsocket" --> AMS
```

---

## 2. 详细交互流程 (Sequence Diagram)

基于 `system/core/debuggerd` 源码深度还原的交互细节，涵盖了信号劫持、双重握手及内存镜像逻辑：

```plantuml
@startuml
!theme plain
scale 1024 width
autonumber

participant "Native Process" as P
participant "Sigchain / Handler" as SH
participant "Pseudothread" as PT
participant "VM Process (Snapshot)" as VM
participant "crash_dump" as CD
participant "tombstoned" as T
participant "ActivityManager" as AMS
participant "Logcat" as LOG

== 1. 信号捕获与环境隔离 ==
P -> P: 发生异常 (e.g., SIGSEGV)
P -> SH: 触发 debuggerd_signal_handler
activate SH

SH -> SH: pthread_mutex_lock (防并发转储)
SH -> LOG: log_signal_summary (Fatal signal...)

note right of SH
  通过 clone(CLONE_VM) 创建伪线程
  不带 CLONE_FILES，拥有独立 FD 表
  以应对 EMFILE 导致的资源耗尽
end note
SH -> PT: clone()
activate PT
SH -> SH: futex_wait (等待 PT 完成)

== 2. 启动调试器与双重握手 ==
PT -> PT: close(0..1023) 暴力清空 FD
PT -> PT: Pipe() 创建进程间通信管道
PT -> CD: execle("/apex/.../crash_dump64")
activate CD

CD -> P: ptrace(PTRACE_SEIZE) 附着崩溃线程
CD -> PT: ptrace(PTRACE_SEIZE, PTRACE_O_TRACECLONE) 监控 PT
CD -> PT: write(pipe, "\1") [握手 1：Ptrace 就绪]

PT -> PT: read(pipe) 阻塞等待
PT -> VM: create_vm_process (Double-fork)
activate VM
note over PT, VM: VM 进程是地址空间的 CoW 镜像\n规避主进程 Mutex 死锁风险

PT -> CD: write(pipe, CrashInfo V4) [握手 2：发送寄存器/元数据]
deactivate PT

== 3. 资源申请与堆栈回溯 ==
CD -> CD: ReadCrashInfo (解析管道数据)
CD -> T: connect_tombstone_server (kDumpRequest)
activate T
T -> T: InterceptCheck (检查 AMS 拦截请求)
T -> T: openat(O_TMPFILE) 分配匿名临时文件
T --> CD: 返回 Text FD & Proto FD
deactivate T

CD -> CD: unwinder.Initialize(VM_PID)
note right of CD: 回溯 VM 进程而非主进程\n彻底解决 dl_lock 竞争导致的挂死
CD -> CD: Unwind Stack (libunwindstack)
CD -> T: Write(FDs) 写入磁盘
CD -> LOG: _LOG (写入 Logcat LOG_ID_CRASH)

== 4. 系统通知与清理 ==
CD -> AMS: activity_manager_notify (ndebugsocket)
activate AMS
AMS --> CD: ACK
deactivate AMS

CD -> T: notify_completion (kCompletedDump)
activate T
T -> T: linkat (原子性重命名临时文件)
deactivate T

CD -> P: ptrace(DETACH)
deactivate CD

SH -> SH: resend_signal (rt_tgsigqueueinfo 重发原始信号)
deactivate SH

P -> P: 内核执行 SIG_DFL，进程彻底终止
@enduml
```

---

## 3. 关键技术实现深度解析

### 3.1 信号劫持层 (Sigchain & Handler)
*   **代码位置**：`art/sigchainlib/sigchain.cc`
*   **机制**：`libsigchain` 劫持了 `sigaction`。ART 注册其处理程序以处理虚函数表修复等逻辑，而 `debuggerd_signal_handler` 被注册为 **Special Handler**。
*   **自愈模式**：Android 14+ 引入 `android_handle_signal`。对于可恢复的 MTE 或 GWP-ASan 故障，调试器生成报告后会修改线程上下文（如禁用 MTE），使信号处理程序返回并恢复应用执行。

### 3.2 伪线程 (Pseudothread) 的设计精髓
*   **资源回收**：崩溃现场可能已耗尽 FD（`EMFILE`）。伪线程通过 `clone` 且不共享 FD 表，进入后执行 `syscall(__NR_close, i)` 暴力腾出空间，确保调试所需的管道和 Socket 能成功创建。
*   **死锁规避**：不使用 `pthread_create` 是为了避免触发 `atfork` 钩子，因为主进程的 `Loader` 锁或堆锁此时可能已被破坏或死锁。

### 3.3 VM Process：无锁镜像技术
*   **实现**：通过 `double-fork` 产生的孤儿进程充当“物理内存快照”。
*   **价值**：`unwindstack` 在回溯损坏的栈帧时需要频繁读取内存。在 VM 进程中读取可以完全规避主进程中因 `dl_lock` 或 `malloc` 锁竞争导致的调试器挂死问题。

### 3.4 运行时元数据注入 (CrashInfo V4)
*   **注入点**：Linker 在启动时通过 `linker_debuggerd_init` 将 `__libc_shared_globals()` 地址传递给 Handler。
*   **内容**：V4 协议不仅传输 `ucontext`，还包含了 **Scudo 分配器状态**、**GWP-ASan 详情**以及 **fdsan 表地址**。这使得 `crash_dump` 能够精准定位 Use-After-Free 或 FD Double Close 等深层内存安全问题。

### 3.5 信号重发与状态还原
*   **rt_tgsigqueueinfo**：调试结束后，Handler 使用此系统调用重发导致崩溃的信号。
*   **意义**：这确保了父进程（Init 或 Zygote）能捕获到真实的退出原因（Exit Status），触发正确的系统重启逻辑。
