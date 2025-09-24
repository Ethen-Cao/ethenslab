+++
date = '2025-08-28T14:30:02+08:00'
draft = false
title = 'Binder'
+++

## 同步通信

![](/ethenslab/images/binder-sync.png)

## 异步通信

![](/ethenslab/images/binder-async.png)

## 内存管理

### **Binder 驱动的通信内存管理机制**

Binder 驱动的内存管理是一套内核层面的复杂机制，其核心目标是在进程间高效、安全地传输数据，并实现“一次拷贝”原则。

#### **第一部分：Binder 通信内存的总体管理机制**

该机制主要分为三个阶段：虚拟内存区的建立、事务缓冲区的分配与映射、以及事务缓冲区的释放。

**1.1 进程虚拟内存区的建立**

当一个用户进程首次打开 `/dev/binder` 设备并对其执行 `mmap()` 系统调用时，Binder 驱动会执行 `binder_mmap()` 内核函数。此函数的主要工作包括：
* 为该进程在内核中创建一个 `binder_proc` 结构体实例，用于追踪其所有 Binder 相关状态。
* 在该进程的虚拟地址空间中，分配并初始化一块指定大小（由 `BINDER_VM_SIZE` 决定，通常为 1MB）的虚拟内存区域（Virtual Memory Area, VMA）。
* 将这个 VMA 与进程的 `binder_proc` 结构体关联。

此阶段的关键在于，**仅分配了虚拟地址空间，并未分配实际的物理内存**。这块 VMA 的作用是为未来接收 Binder 数据提供一个预先确定的目标地址范围。

**1.2 事务缓冲区的分配与映射**

当一个进程（Client）通过 `ioctl(BINDER_WRITE_READ)` 发起一次事务（Transaction）时：
1.  **分配内核缓冲区**：Binder 驱动的 `binder_thread_write()` 函数会调用 `binder_alloc_buf()`，根据事务数据的大小，从内核的通用物理内存池（如 `vmalloc` 或 slab 分配器）中分配一个 `binder_buffer` 内核对象。
2.  **数据拷贝（一次拷贝）**：驱动调用 `copy_from_user()`，将数据从 Client 进程的用户空间地址，拷贝到上一步分配的内核 `binder_buffer` 中。这是整个跨进程通信中唯一的一次数据内容拷贝。
3.  **地址空间映射**：驱动识别出目标进程（Server）后，并不会再次拷贝数据。它会执行一个核心操作：**修改 Server 进程的内核页表**，将承载着数据的 `binder_buffer` 的物理内存页，直接映射到 Server 进程在 1.1 阶段建立的 VMA 中。
4.  **数据投递**：驱动将映射后的缓冲区在 Server 进程中的虚拟地址，连同事务命令（如 `BR_TRANSACTION` 或 `BR_ONEWAY`），一同投递给 Server 中等待的 Binder 线程。Server 线程可以直接访问该地址，如同访问进程内内存一样。

**1.3 事务缓冲区的释放**

当 Server 进程处理完事务数据后，它会通过 `ioctl` 向驱动发送 `BC_FREE_BUFFER` 命令，并附上需要释放的缓冲区的虚拟地址。
* 驱动接收到命令后，调用 `binder_free_buf()` 函数。
* 该函数首先解除该物理内存在 Server 进程 VMA 中的映射（通过修改页表），然后将 `binder_buffer` 对象及其占用的物理内存归还给内核的通用内存池。

---

#### **第二部分：同步与异步消息的内存划分机制**

Binder 驱动对同步和异步消息的内存管理，遵循“**统一物理来源，独立记账配额**”的核心原则。

**2.1 核心原则阐述**

* **统一物理来源**：无论是同步还是异步事务，其 `binder_buffer` 均从上文所述的**同一个内核通用物理内存池**中分配。物理来源上没有划分。
* **独立记账配额**：驱动对每个 `binder_proc`（即每个使用 Binder 的进程）内部，实施了严格独立的会计和配额制度，以此来区分和限制不同类型事务所能占用的内存资源。

**2.2 异步事务的内存配额机制**

为防止非阻塞的异步调用（`oneway`）耗尽系统资源而形成拒绝服务攻击，Binder 驱动对异步事务强制实施了内存配额限制。

* **配额初始化**：在 `binder_mmap()` 阶段，驱动会为进程的 `binder_proc` 结构体初始化一个 `free_async_space` 成员变量。其初始值被设定为该进程总 Binder 缓冲区大小（`buffer_size`）的**一半**。
* **分配时检查**：当 `binder_alloc_buf()` 为一个带有 `TF_ONE_WAY` 标志的异步事务分配缓冲区时，它会执行以下检查：
    * 若请求的缓冲区大小 `size` **大于** 当前可用的 `free_async_space`，分配将失败，内核返回 `-ENOSPC` 错误，该异步事务被丢弃。
    * 若 `size` **小于等于** `free_async_space`，则分配成功，并从配额中扣除相应大小：`free_async_space -= size`。
* **释放时归还**：当 `binder_free_buf()` 释放一个用于异步事务的缓冲区时，会将该缓冲区的大小加回到配额中：`free_async_space += size`。

**2.3 同步事务的内存使用机制**

* 同步事务所请求的内存**不受 `free_async_space` 配额的限制**。
* 其内存使用主要受限于整个进程的总缓冲区大小（`buffer_size`）。由于同步调用会阻塞客户端线程，天然地形成了反向压力（Back-pressure），使其无法在短时间内无限制地消耗内存，因此不需要类似的显式配额限制。

综上所述，Binder 驱动通过 `mmap` 和页表修改实现了高效的“一次拷贝”内存管理。在此基础上，它并未对物理内存池进行划分，而是通过对每个进程实施一个占其总可用缓冲区一半的**异步内存配额**，来精确地约束和管理同步与异步消息的资源使用，确保系统的稳定性和公平性。

## Debug

以下是导致 oneway Binder 调用失败的主要原因，从最常见到最少见排列：

### 1\. 目标进程（B进程）不存在或已死亡

这是最常见的原因。如果 B 进程由于崩溃、被系统杀死（例如，低内存时）或者正常退出，而 A 进程仍然持有一个指向 B 进程服务的 Binder 代理对象，那么当 A 进程尝试通过这个代理发送消息时，Binder 驱动会发现目标进程已经不存在了。

  * **返回错误**: 调用会立即失败，通常 JNI 层会抛出 `DeadObjectException`，底层返回的错误码是 `DEAD_OBJECT`。
  * **如何排查**:
      * 检查 Logcat，过滤 B 进程的 PID 或者应用名，看是否有崩溃日志或 `Process ended` 的信息。
      * 在 Logcat 中搜索 `DeadObjectException` 关键字。
  * **解决方案**: A 进程应该实现 `IBinder.DeathRecipient` 接口，并调用 `binder.linkToDeath()` 来监听 B 进程的死亡通知。在收到 `binderDied()` 回调后，A 进程应该清理掉旧的 Binder 代理对象，并在需要时重新获取服务。


    ```java
    // 示例代码
    private IBinder.DeathRecipient mDeathRecipient = new IBinder.DeathRecipient() {
        @Override
        public void binderDied() {
            if (mService != null) {
                mService.asBinder().unlinkToDeath(this, 0);
                mService = null;
                // 在这里执行重新连接服务的逻辑
            }
        }
    };

    // 获取服务后
    mService.asBinder().linkToDeath(mDeathRecipient, 0);
    ```

### 2\. Binder 事务缓冲区已满

Binder 通信依赖于一块内核管理的共享内存作为缓冲区。虽然 oneway 调用不需要等待 B 进程处理完，但它仍然需要将数据（方法标识符和参数）从 A 进程复制到这个内核缓冲区。

如果 B 进程非常繁忙，或者有大量的进程（包括 A 进程）在短时间内向 B 进程发送了大量的 Binder 消息（无论是 oneway 还是双向的），就可能导致分配给 B 进程的 Binder 缓冲区被占满。当 A 进程再次尝试发送 oneway 消息时，内核无法为其分配空间，调用就会失败。

  * **返回错误**: 底层返回 `BR_FAILED_REPLY` 或 `FAILED_TRANSACTION`。
  * **如何排查**:
      * 使用 `adb shell dumpsys binder` 或 `adb shell cat /sys/kernel/debug/binder/stats` 查看 Binder 的统计信息，关注失败的事务（failed transactions）数量。
      * 检查 B 进程是否有 ANR（Application Not Responding），如果 B 进程的主线程或 Binder 线程池被阻塞，它就无法及时处理收到的事务，导致缓冲区堆积。

### 3\. 事务数据过大

Binder 事务能够承载的数据量是有限的，这个限制通常是 1MB 左右（实际上是整个 Binder 缓冲区的一部分）。如果你尝试在 oneway 调用中传递一个非常大的对象（例如一个巨大的 Bitmap 或 List），超过了这个限制，事务在发送阶段就会失败。

  * **返回错误**: 底层会返回 `TRANSACTION_TOO_LARGE` 错误，Java 层会抛出 `TransactionTooLargeException`。
  * **如何排查**:
      * 在 Logcat 中直接搜索 `TransactionTooLargeException`。
      * 检查你通过 oneway 调用传递的数据大小。如果是图片或文件，应考虑使用其他 IPC 方式，如共享内存（Ashmem）或文件描述符（File Descriptor）。

### 4\. 目标进程（B进程）无响应 (ANR)

即使 B 进程还活着，但如果它的 Binder 线程池中的所有线程都被长时间运行的任务占用了，或者主线程发生了 ANR，那么它就无法处理新的 Binder 请求。这会间接导致第 2 点中提到的“Binder 事务缓冲区已满”问题。ANR问题可能导致线程阻塞，间接导致异步线程处理能力下降。

对于 oneway 调用来说，A 进程虽然不会被阻塞，但 Binder 驱动发现无法将消息派发给 B 进程的任何一个空闲线程时，可能会导致后续的调用失败（缓冲区满）。

  * **如何排查**: 在 `/data/anr/traces.txt` 文件中查找 B 进程的 ANR 日志，分析其线程堆栈，看 Binder 线程是否被卡住。

### 5\. SELinux 权限问题

在现代 Android 系统中，SELinux（安全增强型 Linux）对进程间的通信有严格的访问控制。如果 A 进程的 SELinux 上下文没有被授予向 B 进程的服务发起 Binder 调用的权限，那么这个调用在内核层面就会被拒绝。

  * **返回错误**: 通常是 `PERMISSION_DENIED`。
  * **如何排查**: 在 Logcat 中过滤 `avc: denied` 关键字。SELinux 的拒绝日志会清晰地标明源上下文（source context, A进程）、目标上下文（target context, B进程）以及缺少的权限。

### 总结

总的来说，oneway Binder 调用失败的原因可以归结为以下几点：

| 失败原因 | 关键错误/日志 | 常见场景 |
| :--- | :--- | :--- |
| **目标进程死亡** | `DeadObjectException` | B 进程崩溃或被系统杀死。 |
| **Binder 缓冲区满** | `FAILED_TRANSACTION` | B 进程处理慢，或短时请求过多。 |
| **传输数据过大** | `TransactionTooLargeException` | 传递了超过 1MB 的大数据。 |
| **目标进程无响应** | B 进程的 ANR 日志 | B 进程 Binder 线程池或主线程阻塞。 |
| **SELinux 权限不足** | `avc: denied` | 缺少正确的 SELinux 策略规则。 |

排查时，**首先应该检查 Logcat**，因为绝大多数问题（如进程死亡、数据过大、权限问题）都会在日志中留下明确的线索。如果日志没有直接线索，再考虑是否是由于 B 进程无响应导致的缓冲区溢出。