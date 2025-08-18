+++
date = '2025-08-03T17:17:50+08:00'
draft = false
title = 'QNX Screen基础原理与流程'
+++


## QNX图形栈

![screen_post_window](/ethenslab/images/qnx-screen-overview.png)

一个 QNX 应用程序从无到有，完成一帧 (frame) 窗口渲染并显示在屏幕上的完整过程。

整个过程可以分为两个核心阶段：
1.  **准备与渲染阶段**：应用程序获取绘图空间 (Buffer)，并使用 GPU 将内容绘制到这个空间中。
2.  **提交与显示阶段**：应用程序通知系统绘制完成，由系统和硬件接手，将内容呈现在屏幕上。



### 第一阶段：准备与渲染 (Steps 1-6)

#### **步骤 1 & 2：请求并获取窗口缓冲区 (Buffer)**
* **执行者**：`QNX Application`, `QNX Screen`
* **关键 API**：`screen_create_window_buffers()`

一个应用程序（例如 HMI 界面）首先需要一块“画布”来进行绘制。它会调用 QNX Screen 提供的 API，请求创建一个窗口以及与之关联的一组（通常是两个或三个，用于实现双缓冲/三缓冲技术）图形缓冲区 (Framebuffers)。

`QNX Screen` 作为窗口系统管理者，并不会自己分配这块特殊的内存。它会通过 IPC (进程间通信) **请求** `Display/GPU Driver` (资源管理器) 来分配。驱动程序会分配一块符合硬件要求（例如物理上连续）的共享内存，并将其句柄 (handle) 返回给 `Screen`。最后，`Screen` 再将代表这些 Buffer 的句柄返回给应用程序。至此，应用程序拥有了可以在上面作画的“画布”。

#### **步骤 3 & 4：提交绘图指令**
* **执行者**：`QNX Application`, `Graphics API (OpenGL ES + EGL)`, `GPU Driver`
* **关键 API/机制**：`eglSwapBuffers()`, QNX IPC (`msg`/`devctl`)

应用程序使用像 OpenGL ES 这样的标准图形 API 来描述要绘制的内容（例如按钮、仪表盘、3D 模型等）。这些 API 调用定义了图元的形状、纹理和颜色。

当应用程序完成一帧的全部绘图指令描述后，它会调用一个像 `eglSwapBuffers()` 这样的关键函数。这个函数的调用意味着“我已经定义好这一帧的所有内容了”。EGL 函数库会将这些高级的绘图指令打包，通过 QNX 的 IPC 机制（通常是 `devctl`），将指令发送到 `GPU Driver` 这个独立的用户空间进程。

#### **步骤 5 & 6：硬件加速渲染**
* **执行者**：`GPU Driver`, `GPU (Hardware)`, `Framebuffers (Shared Memory)`

`GPU Driver` 进程接收到来自 EGL 的绘图指令。它的职责是将这些指令翻译成 GPU 硬件能直接执行的命令。接着，驱动程序会通过微内核仲裁来获得对硬件的访问权，并将这些命令提交给 `GPU`。

`GPU` 是一个高度并行化的处理器，它会极速执行这些命令，进行顶点变换、光栅化、着色等一系列运算。最终，GPU 将计算出的像素颜色值，通过直接内存访问 (DMA) 的方式，**直接写入**到步骤 2 中分配好的那个离屏缓冲区 (off-screen buffer) 中。这个过程 CPU 基本不参与，效率极高。

**至此，新的一帧画面已经在一个用户看不见的内存缓冲区中准备就绪。**


### 第二阶段：提交与显示 (Steps 7-12)

#### **步骤 7：通知绘制完成**
* **执行者**：`QNX Application`, `QNX Screen`
* **关键 API**：`screen_post_window()`

`eglSwapBuffers()` 函数在内部通常会触发 `screen_post_window()` 的调用。这是整个流程中的**关键交接点**。应用程序通过这个 API 调用，正式通知 `QNX Screen`：“我已经画好了，这个 Buffer 现在归你了，你可以拿去显示了”。完成通知后，应用程序就可以立即使用另一个空闲的 Buffer 来开始准备下一帧的内容，实现流畅的动画效果。

#### **步骤 8 & 9：更新显示管线**
* **执行者**：`QNX Screen`, `OpenWFD Driver`, `Display Driver`
* **关键 API/机制**：`wfdDeviceCommit()`, `devctl`

`QNX Screen` 作为画面合成器 (Compositor)，接收到来自应用程序的通知。它会根据窗口的层级、可见性等状态，决定何时更新屏幕。当决定更新时，它会调用 `OpenWFD` 函数库提供的 API（例如 `wfdDeviceCommit`）。

`OpenWFD` 函数库会将这个高级的显示请求，转换成一个具体的 `devctl` 指令，发送给 `Display Driver` 这个用户空间进程。这个指令的核心内容是：“请将屏幕上的第 N 层 (Layer)，指向这个新的 Buffer 的物理地址”。

#### **步骤 10：更新显示控制器 (指针翻转)**
* **执行者**：`Display Driver`, `Display Controller (Hardware)`

`Display Driver` 接收到指令后，它的任务非常单纯且关键：与硬件通信。它会向 `Display Controller` 硬件的特定寄存器写入一个新的内存地址——也就是那块已经绘制好内容的新 Buffer 的起始地址。

这个操作被称为 **“指针翻转”(Pointer Flip)**。它本身几乎不耗费任何时间，因为没有复制任何像素数据，仅仅是改变了一个指针。

#### **步骤 11 & 12：硬件扫描输出**
* **执行者**：`Display Controller (Hardware)`, `Framebuffers`, `Physical Display`

`Display Controller` 是一个独立工作的硬件单元。它会以固定的频率（例如 60Hz）不断地从它被告知的内存地址开始，逐行读取像素数据，这个过程称为“扫描输出”(Scanout)。

在下一个刷新周期（例如未来的 1/60 秒内），`Display Controller` 就会自动地从步骤 10 设置的**新地址**开始读取数据。读取到的像素数据被转换成视频信号（如 HDMI），最终发送到实体屏幕上。

**至此，用户终于在屏幕上看到了应用程序绘制的新画面。整个高效、流畅的渲染流程宣告完成。**

## screen_post_window

![screen_post_window](/ethenslab/images/qnx-screen-screen_post_window.png)
