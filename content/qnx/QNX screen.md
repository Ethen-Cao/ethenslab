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

##### eglSwapBuffers() 的作用

eglSwapBuffers() 不是把图像“提交给 GPU”，而是：

* Flush/提交之前累积的 OpenGL ES 命令，告诉 GPU 驱动“这些命令可以执行了”。

* 交换前后缓冲区：把渲染目标从后台 buffer 翻转成前台 buffer。对 QNX/高通平台：这一步完成后，GPU 开始执行命令，把结果真正写进后台 buffer（即 framebuffer）。
    
在 QNX + 高通平台下，后台 buffer 的分配路径大致如下：

* 应用创建 EGL surface 或 QNX Screen window：调用 eglCreateWindowSurface() 或 screen_create_window_buffers()。
* Screen 负责分配 buffer：Screen 作为窗口系统和 buffer allocator，会根据需求分配 2～3 个 buffer（双缓冲或三缓冲）。

分配时考虑：

* 必须是 物理可连续 / 可 DMA 的内存
* 必须满足 GPU tiling/对齐要求
* 必须能被 Display Controller 直接 scanout

底层内存分配机制

在高通 BSP 中，这一步通常通过 ION/DMABUF 完成：

* ION/DMABUF 分配一块显存
* 返回一个 fd / handle
* Screen 管理这些 handle，并把它映射到 EGL/应用进程的地址空间
* 应用得到 buffer handle
* 应用最终拿到的不是“物理地址”，而是一个 handle (screen_buffer_t) 或 EGL surface 绑定的 framebuffer。
* GPU driver 使用这个 handle 来写像素，Display driver 使用同一个 handle 来做 scanout。

##### Fence同步

* 异步执行与 Fence 创建：eglSwapBuffers() 的核心就是将渲染任务“提交”出去，然后立即返回，让应用程序（CPU）可以继续处理下一帧的逻辑。GPU Driver 在接收到任务后，会创建一个与该任务关联的 Fence，这个 Fence 相当于一个“任务完成的回执单”。
* Fence 的传递：
    * EGL 在把 buffer 返回给 Screen 时，会把这个 Fence 一起交给 Screen。
    * Screen 在调用 OpenWFD / Display Driver 时，会附带这个 Fence。
    * Display Driver 不会立刻用 buffer，而是等待 Fence signal 触发（即 GPU 真正画完）后，才做 pointer flip
* 等待与执行：Display Driver 作为消费者，拿到了这个“带条件”的 Buffer。它不会盲目地直接将其用于显示。它会等待这个 Fence 发出信号（signaled），这个信号的含义就是“GPU 已经画完了，这个 Buffer 的内容是完整且有效的”。只有确认了这一点，Display Driver 才会安全地执行 Pointer Flip，让显示控制器去读取这块内存。

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


## opengles & EGL

在图形编程里 **OpenGL ES** 和 **EGL** 经常一起出现，但它们的职责完全不同：


### 🔹 1. **OpenGL ES**

* **全称**：OpenGL for Embedded Systems
* **定位**：一个 **图形渲染 API**
* **作用**：

  * 提供一套函数（API），让应用能调用 GPU 来做 **绘制**。
  * 主要负责 **"画什么"**：三角形、纹理、光照、着色器等。
* **核心功能**：

  * 定义图形流水线（顶点着色器、片段着色器）。
  * 绘制 2D/3D 图形。
  * 控制渲染状态、纹理、FrameBuffer 等。
* **类比**：像一个画家，专注于如何画图。

👉 **但 OpenGL ES 自己并不知道图要画到哪儿去（屏幕？窗口？内存？）**


### 🔹 2. **EGL**

* **全称**：Embedded-System Graphics Library (不是 OpenGL 的子集，独立标准)
* **定位**：**上下文管理 & 平台接口库**
* **作用**：

  * 负责 **"在哪里画、怎么画"**。
  * 建立应用和底层窗口系统/驱动之间的桥梁。
* **核心功能**：

  1. **连接窗口系统**（比如 Android 的 SurfaceFlinger / Linux 的 X11 / Wayland / QNX Screen）。
  2. **创建渲染上下文**（OpenGL ES 必须依赖一个 Context 才能工作）。
  3. **管理 Surface**（屏幕上的窗口、离屏缓冲区等）。
  4. **缓冲区交换**（`eglSwapBuffers()`，把 GPU 渲染结果显示到屏幕）。
* **类比**：像一个舞台管理者，负责搭建舞台、安排画布，最后通知观众看画。

👉 **EGL 不负责绘图，它只提供“画布+上下文+显示通道”。绘制的动作要靠 OpenGL ES。**

---

### 🔹 3. 关系

* **应用** → 调用 EGL：

  * 选一个显示系统的窗口 / Surface。
  * 创建一个 EGLContext。
* **应用** → 使用 OpenGL ES：

  * 在 EGLContext 里调用 `glDrawArrays()`、`glDrawElements()` 之类的函数来画图。
* **应用** → 调用 EGL：

  * `eglSwapBuffers()` 把绘制结果显示出来。

---

### 🔹 4. 举个例子（Android / QNX）

1. EGL：连接到 SurfaceFlinger / QNX Screen，分配缓冲区，创建 EGLContext。
2. OpenGL ES：用着色器绘制一个三角形到缓冲区。
3. EGL：调用 `eglSwapBuffers()` 把三角形送到显示器。


✅ **一句话总结**

* **OpenGL ES** = 画图工具（怎么画）
* **EGL** = 舞台管理（在哪画 & 把图送到屏幕）

![](/ethenslab/images/opengles-drawing-process.png)


