+++
date = '2025-09-28T11:36:11+08:00'
draft = false
title = 'Binder spam detection原理'
+++

## Binder spam detection原理

当Binder异步通信消耗了过多的binder buffer的时候，会打印出如下log:

```
IPCThreadState: Process seems to be sending too many oneway calls.
```

### 核心原因

这个日志的根本原因在于 **Kernel 层的 Binder 驱动程序** 检测到某个进程发送了过多的 oneway（异步）调用，导致为 oneway 调用预留的 **异步缓冲区空间 (async space) 严重不足**。这是一种保护机制，旨在防止某个进程因滥发 oneway 调用而耗尽 Binder 资源，影响系统其他进程的正常通信。

整个检测和通知流程可以概括为：

1.  **客户端发起 Oneway 调用**：进程通过 `transact()` 发起一个带有 `TF_ONE_WAY` 标志的 Binder 调用。
2.  **内核分配缓冲区**：Binder 驱动在内核空间为这个 oneway 事务分配内存。
3.  **内核进行垃圾邮件检测 (Spam Detection)**：在分配内存时，内核会检查剩余的**异步缓冲区空间**。如果空间低于某个阈值（总空间的 10%），驱动就会开始怀疑有进程在“滥发” oneway 调用。
4.  **标记可疑事务**：如果异步空间过低，驱动会进一步检查当前发起调用的这个进程，是否占用了过多的 oneway 缓冲区（例如，超过 50 个缓冲区或总大小超过总空间的 25%）。如果满足条件，内核就会给这个事务的缓冲区打上 `oneway_spam_suspect` 的标记。
5.  **内核返回特殊指令**：对于一个 oneway 调用，内核需要立即给客户端一个“完成”回执。此时，如果发现事务缓冲区有 `oneway_spam_suspect` 标记，内核就不会返回常规的 `BR_TRANSACTION_COMPLETE`，而是返回一个特殊的 `BR_ONEWAY_SPAM_SUSPECT` 指令。
6.  **用户空间打印日志**：客户端的 `IPCThreadState` 在 `waitForResponse()` 中接收并解析来自内核的指令。当它收到 `BR_ONEWAY_SPAM_SUSPECT` 时，就会打印出这条我们看到的错误日志。

### 代码分析

  * **用户空间日志打印点 (IPCThreadState.cpp)**
    在 `IPCThreadState::waitForResponse` 函数中，它处理从 Binder 驱动返回的各种指令 (`BR_*`)。其中就包括 `BR_ONEWAY_SPAM_SUSPECT`。

    ```cpp
    // IPCThreadState.cpp
    status_t IPCThreadState::waitForResponse(Parcel *reply, status_t *acquireResult)
    {
        // ...
        while (1) {
            // ...
            cmd = (uint32_t)mIn.readInt32();
            // ...
            switch (cmd) {
            case BR_ONEWAY_SPAM_SUSPECT:
                ALOGE("Process seems to be sending too many oneway calls."); // <-- 日志打印点
                CallStack::logStack("oneway spamming", nullptr,
                    ANDROID_LOG_ERROR);
                [[fallthrough]];
            case BR_TRANSACTION_COMPLETE:
                if (!reply && !acquireResult) goto finish;
                break;
            // ...
            }
        }
        // ...
    }
    ```

  * **内核空间检测逻辑 (binder\_alloc.c)**
    内核中的 `binder_alloc_new_buf_locked` 函数在为 oneway 事务分配缓冲区时，会调用 `debug_low_async_space_locked` 进行检测。

    ```c
    // binder_alloc.c
    static struct binder_buffer *binder_alloc_new_buf_locked(
                    ..., int is_async)
    {
        // ...
        if (is_async) {
            alloc->free_async_space -= size; // 减少可用的异步空间
            // ...
            if (debug_low_async_space_locked(alloc))
                buffer->oneway_spam_suspect = true; // <-- 如果检测为 spam，设置标记
        }
        // ...
        return buffer;
    }

    static bool debug_low_async_space_locked(struct binder_alloc *alloc)
    {
        // ...
        // 阈值1：只有当可用异步空间低于总空间的10%时，才开始检测
        if (alloc->free_async_space >= alloc->buffer_size / 10) {
            alloc->oneway_spam_detected = false;
            return false;
        }

        // ... 计算当前进程已分配的 oneway 缓冲区数量和总大小

        // 阈值2：如果进程的 oneway 缓冲区超过50个或总大小超过总空间的25%
        if (num_buffers > 50 || total_alloc_size > alloc->buffer_size / 4) {
            // ...
            if (!alloc->oneway_spam_detected) {
                alloc->oneway_spam_detected = true;
                return true; // <-- 返回 true，表示检测到 spam
            }
        }
        return false;
    }
    ```

-----

### Spam detection 时序图

![](/ethenslab/images/spam-detection.png)


## IPCThreadState CallStack retun null的原因

在IPCThreadState接收到驱动返回的BR_ONEWAY_SPAM_SUSPECT后，调用了CallStack的logStack打印出调用进程的堆栈。代码如下：

```cpp
        switch (cmd) {
        case BR_ONEWAY_SPAM_SUSPECT:
        ALOGE("Process seems to be sending too many oneway calls.");
        CallStack::logStack("oneway spamming", nullptr,
            ANDROID_LOG_ERROR);
            [[fallthrough]];
```

但在user版本中，堆栈并没有打印成功，而是打印了：**CallStack::getCurrentInternal not linked, returning null**，这又是为什么呢？

### 原因分析

在 **AOSP** 中：

* **`libbinder`** 负责 Binder IPC，`IPCThreadState` 是其核心类之一。

* 当 Binder 检测到 oneway 调用发送过于频繁时，会触发 `BR_ONEWAY_SPAM_SUSPECT`。

* 为了调试，`libbinder` 会尝试打印调用堆栈，调用 `CallStack::getCurrent()` 或 `CallStack::logStack()`。

* **`CallStack` 的实现是弱符号**，定义在 `libutilscallstack.so` 中：

  ```cpp
  static CallStackUPtr CALLSTACK_WEAK getCurrentInternal(int32_t ignoreDepth);
  static void CALLSTACK_WEAK logStackInternal(...);
  ```

* 在 `libbinder` 中：

  ```cpp
  auto stack = CallStack::getCurrent().get();
  CallStack::logStack("oneway spamming", stack, ANDROID_LOG_ERROR);
  ```

* 弱符号的特性：

  * 如果没有真正被链接（动态库未加载或者未导出符号），函数指针为 `nullptr`。
  * `CallStack` 内部有保护逻辑：

    ```cpp
    if (reinterpret_cast<uintptr_t>(getCurrentInternal) == 0) {
        ALOGW("CallStack::getCurrentInternal not linked, returning null");
    }
    if (reinterpret_cast<uintptr_t>(logStackInternal) == 0) {
        ALOG(LOG_WARN, logtag, "CallStack::logStackInternal not linked");
    }
    ```

---

发生原因：

1. `IPCThreadState` 调用了 `CallStack::getCurrent()`。
2. `CallStack::getCurrent()` 内部依赖 **弱符号 `getCurrentInternal`**。
3. 弱符号定义在 `libutilscallstack.so` 中，但 **libbinder在user版本没有链接 libutilscallstack**。
4. 动态链接器查找全局符号表：

   * 进程自身（EXE）没有符号
   * 已加载的库（此时 libutilscallstack 没有加载）
   * 找不到 → 弱符号指针为 `nullptr`
5. `CallStack::getCurrent()` 检测到 `nullptr` → 打印日志，并返回空指针。


### Demo演示

### 概览
- 目的：演示 C/C++ 中的弱符号（weak symbol）如何用于可选回调实现，以及链接器/运行时加载决策（DT_NEEDED / --as-needed）如何影响弱符号在运行时是否被解析。
- 核心文件：
  - a.h — 弱符号声明：`weak_function`；以及库接口 `call_from_a()`
  - a.cpp — `call_from_a()` 的实现，调用前检查 `weak_function`
  - b.cpp / b.h — `weak_function` 的强实现
  - main.cpp — 程序入口：调用 `call_from_a()`
  - Makefile — 构建两个可执行文件 main1（只链接 liba）和 main2（链接 liba 与 libb，并通过链接器选项确保 libb 被记录为运行时依赖）
  - 可执行文件：main1、main2

### 设计要点（简明）
- 在 a.h 中使用 `__attribute__((weak))` 声明 `weak_function`，使其成为弱符号；若进程中存在该符号的强实现（例如在 libb 中），运行时会使用强实现，否则弱符号地址为 NULL。
- 问题点：即便在链接命令中写了 `-lb`，链接器的默认行为（--as-needed）可能不会把 `libb.so` 写入可执行文件的 DT_NEEDED（因为可执行文件本身不直接引用 libb，而是由 liba 间接引用）。结果运行时不会自动加载 libb，弱符号仍然为 NULL。
- 解决办法（示例中）：在生成 main2 时使用 -Wl,--no-as-needed -lb -Wl,--as-needed 来强制将 libb 写入 DT_NEEDED（详见 Makefile 中的注释与命令）。

### 如何构建
- 在工程根目录运行：

```sh
# ...existing code...
make clean
make
```

（参见 Makefile 以及子目录 Makefile 和 Makefile）

运行与验证步骤
1. 运行只链接 liba 的可执行：main1。

    ```sh
    # ...existing code...
    ./main1
    ```

预期输出（main1，不加载 libb）：
- [liba] call_from_a() called
- [liba] weak_function is NOT defined

原因：main1 的 DT_NEEDED 不包含 libb（见下），运行时不会加载 libb.so，`weak_function` 在运行时为 NULL，a 中做了空指针检查所以不会调用。

2. 检查 main1 的运行时依赖（DT_NEEDED）：

    ```sh
    # ...existing code...
    readelf -d ./main1 | grep NEEDED
    ```

预期结果：只看到 liba（和系统库），没有 libb。

3. 运行链接了 libb 的可执行：main2。

    ```sh
    # ...existing code...
    ./main2
    ```

预期输出（main2，加载 libb）：
- [liba] call_from_a() called
- [liba] weak_function is defined, calling it...
- [libb] weak_function() implementation called!

原因：在 Makefile 中生成 main2 时使用了 -Wl,--no-as-needed -lb -Wl,--as-needed，因此 libb 被记录在 DT_NEEDED，运行时加载 libb.so，`weak_function` 被解析为 libb 的强实现。

4. 检查 main2 的运行时依赖（DT_NEEDED）确认 libb 被记录：

    ```sh
    # ...existing code...
    readelf -d ./main2 | grep NEEDED
    ```

预期结果：能看到 libb.so 出现在 NEEDED 条目中（以及 liba.so 等）。

进一步的静态/动态检查
- 查看 liba.so 中对 weak symbol 的引用：

    ```sh
    # ...existing code...
    readelf -Ws liba/liba.so | grep weak_function
    ```

- 查看 libb.so 导出的符号：

    ```sh
    # ...existing code...
    nm -D libb/libb.so | grep weak_function
    ```

总结：
- weak symbol 的常见用途：可选回调、插件式可插拔实现、后向兼容等。
- 运行时解析依赖于进程地址空间是否载入了提供强定义的共享对象；仅仅在链接阶段写 `-lb` 并不总是能保证运行时加载 libb（取决于链接器的 as-needed 行为）。

### 代码结构和文件

```
weak_symbols$ tree
.
├── liba
│   ├── a.cpp
│   ├── a.h
│   ├── liba.so
│   └── Makefile
├── libb
│   ├── b.cpp
│   ├── b.h
│   ├── libb.so
│   └── Makefile
├── main1
├── main2
├── main.cpp
└── Makefile

3 directories, 12 files
```

---
liba/a.h

```cpp
#pragma once
#include <string>

// 声明一个弱符号函数
// 说明：
//  1) `__attribute__((weak))` 将符号声明为“弱符号”。如果在链接时或运行时
//     找不到该符号的强定义（strong definition），弱符号可以被视为未定义而
//     不会产生链接错误（与普通未定义符号不同，普通未定义符号会导致链接失败）。
//  2) 运行时行为：如果进程的地址空间中存在该符号的强定义（例如由另一个共享库
//     `libb.so` 提供并被加载到进程中），那么该强定义会被使用；否则弱符号的地址
//     为 NULL（或等价的未定义），调用前通常要先检查（如 `if (weak_function)`）。
//  3) 与共享库结合使用时的常见陷阱：即便在链接阶段命令里写了 `-lb`，链接器可能
//     （在默认的 --as-needed 行为下）并不会把 `libb.so` 写入最终可执行文件的 DT_NEEDED
//     条目——尤其当可执行文件本身并不直接引用 `libb` 中的符号，而是 `liba.so`
//     间接引用时。结果运行时不会自动加载 `libb`，导致弱符号仍然为 NULL。请参考
//     示例仓库中的 Makefile 链接选项：可以用 `-Wl,--no-as-needed -lb -Wl,--as-needed`
//     来强制记录 `libb.so` 为运行时依赖，或在程序里显式 dlopen `libb.so`。
//  4) 推荐用法：如果你依赖另一个库来提供可选的回调实现，使用弱符号并在调用前
//     做空指针检查是一种常见做法；但同时要保证运行时能把提供实现的库加载进来，
//     否则该实现永远不会被调用。
__attribute__((weak)) void weak_function();

// A库提供的接口
void call_from_a();

```

---
liba/a.cpp

```cpp
#include "a.h"
#include <iostream>

void call_from_a() {
    std::cout << "[liba] call_from_a() called" << std::endl;
    if (weak_function) {
        std::cout << "[liba] weak_function is defined, calling it..." << std::endl;
        weak_function();
    } else {
        std::cout << "[liba] weak_function is NOT defined" << std::endl;
    }
}
```

---
liba/Makefile

```Makefile
CXX := g++
CXXFLAGS := -Wall -fPIC -O2
TARGET := liba.so

all: $(TARGET)

$(TARGET): a.cpp a.h
	$(CXX) $(CXXFLAGS) -shared a.cpp -o $@

clean:
	rm -f $(TARGET) *.o
```

---
lib/b.h

```cpp
#pragma once
#include <string>

// libb 提供 weak_function 的实现
void weak_function();
```

lib/b.cpp
```
#include "b.h"
#include <iostream>

void weak_function() {
    std::cout << "[libb] weak_function() implementation called!" << std::endl;
}
```

lib/Makefile
```Makefile
CXX := g++
CXXFLAGS := -Wall -fPIC -O2
TARGET := libb.so

all: $(TARGET)

$(TARGET): b.cpp b.h
	$(CXX) $(CXXFLAGS) -shared b.cpp -o $@

clean:
	rm -f $(TARGET) *.o

```

---
main.cpp
```cpp
#include "liba/a.h"

int main() {
    call_from_a();
    return 0;
}
```

顶层 Makefile

```Makefile
CXX := g++
LDFLAGS := -L./liba -L./libb
INCLUDES := -I./liba -I./libb

all: main1 main2

# 只链接 liba
main1: main.cpp liba/liba.so
	$(CXX) main.cpp -o $@ $(INCLUDES) $(LDFLAGS) -la -Wl,-rpath=./liba

# 链接 liba 和 libb
main2: main.cpp liba/liba.so libb/libb.so
	# Ensure libb is recorded in DT_NEEDED so the runtime linker loads it.
	# Use --no-as-needed/--as-needed around -lb to prevent the linker from
	# dropping libb when its symbols aren't directly referenced by the main
	# binary (they're referenced by liba instead).
	$(CXX) main.cpp -o $@ $(INCLUDES) $(LDFLAGS) -la -Wl,--no-as-needed -lb -Wl,--as-needed -Wl,-rpath=./liba:./libb

liba/liba.so:
	$(MAKE) -C liba

libb/libb.so:
	$(MAKE) -C libb

clean:
	$(MAKE) -C liba clean
	$(MAKE) -C libb clean
	rm -f main1 main2

```