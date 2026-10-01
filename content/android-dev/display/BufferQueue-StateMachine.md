# 深入理解 BufferQueue 状态机

## 一、核心状态定义

在 BufferQueue 中，每个 Buffer Slot 的状态由一个计数器三元组 `(mDequeueCount, mQueueCount, mAcquireCount)` 以及 `mShared` 标志位共同决定。具体分为以下 5 种核心状态：

| 状态 | 标识位 (mShared) | Dequeue 计数 | Queue 计数 | Acquire 计数 | 当前持有者 |
|---|:---:|:---:|:---:|:---:|---|
| **FREE** | false | 0 | 0 | 0 | **BufferQueue** |
| **DEQUEUED** | false | 1 | 0 | 0 | **Producer** (App 渲染线程) |
| **QUEUED** | false | 0 | 1 | 0 | **BufferQueue** |
| **ACQUIRED** | false | 0 | 0 | 1 | **Consumer** (SurfaceFlinger) |
| **SHARED** | true | 任意 | 任意 | 任意 | **Producer & Consumer** (共享模式) |

### 状态详解：
- **FREE (空闲)**：Buffer 完全由 BufferQueue 拥有，随时可以被 Producer 申请（Dequeue）。
- **DEQUEUED (已出队)**：Producer 成功申请了该 Buffer，目前由 Producer 独占。Producer 必须等待相关的 Release Fence 发出信号后，才能安全地向其中写入数据。
- **QUEUED (已入队)**：Producer 完成了绘制并将 Buffer 交还给 BufferQueue 排队。此时 Buffer 内容已就绪，但 Consumer 必须等待 Acquire Fence 发出信号才能读取。
- **ACQUIRED (已获取)**：Consumer (如 SurfaceFlinger) 拿到了该 Buffer 进行合成或显示。当消费完成后，Consumer 会将其释放回 FREE 状态。
- **SHARED (共享)**：特殊模式，允许多个组件同时并发访问该 Buffer（不仅限于单一状态）。

---

## 二、状态流转与核心 API

Buffer 的生命周期本质上是 Producer 和 Consumer 之间的数据传递过程。以下是完整的状态转换图及其对应的核心 API。

### 1. 完整状态机图谱

```mermaid
stateDiagram-v2
    direction TB

    [*] --> FREE : 初始分配 (GraphicBuffer)

    FREE --> DEQUEUED : dequeueBuffer()
    DEQUEUED --> QUEUED : queueBuffer()
    QUEUED --> ACQUIRED : acquireBuffer()
    ACQUIRED --> FREE : releaseBuffer()

    DEQUEUED --> FREE : cancelBuffer()
    QUEUED --> FREE : async 模式丢帧 / drop stale

    DEQUEUED --> [*] : detachBuffer() (Producer)
    ACQUIRED --> [*] : detachBuffer() (Consumer)
    
    [*] --> DEQUEUED : attachBuffer() (Producer)
    [*] --> ACQUIRED : attachBuffer() (Consumer)
```

### 2. API 转换详情表

| 转换路径 | 触发 API | 内部调用方法 | 源码位置 (`frameworks/native/libs/gui/`) |
|---|---|---|---|
| FREE → DEQUEUED | `dequeueBuffer()` | `mBufferState.dequeue()` | `BufferQueueProducer.cpp:577` |
| DEQUEUED → QUEUED | `queueBuffer()` | `mBufferState.queue()` | `BufferQueueProducer.cpp:1060` |
| QUEUED → ACQUIRED | `acquireBuffer()` | `mBufferState.acquire()` | `BufferQueueConsumer.cpp:288` |
| ACQUIRED → FREE | `releaseBuffer()` | `mBufferState.release()` | `BufferQueueConsumer.cpp:527` |
| DEQUEUED → FREE | `cancelBuffer()` | `mBufferState.cancel()` | `BufferQueueProducer.cpp:1271` |
| QUEUED → FREE | 被覆盖 / 丢弃 | `mBufferState.freeQueued()` | `BufferQueueProducer.cpp:1119` & `BufferQueueConsumer.cpp:187` |

---

## 三、Fence 语义与所有权转移

在异步渲染架构中，状态的改变（CPU 侧）并不代表 GPU 侧的工作已经完成。**所有权转移的安全性完全依赖于 Fence 机制**。

```mermaid
sequenceDiagram
    participant P as Producer (App / GPU)
    participant BQ as BufferQueue
    participant C as Consumer (SurfaceFlinger)

    Note over BQ: Slot 处于 FREE 状态<br/>(mFence = Release Fence)
    P->>BQ: dequeueBuffer()
    BQ-->>P: 返回 Buffer & outFence (Release Fence)
    Note over P: Slot 处于 DEQUEUED 状态<br/>Producer 侧 GPU 等待 outFence 信号<br/>信号到达后开始渲染

    P->>BQ: queueBuffer(acquireFence)
    Note over BQ: Slot 处于 QUEUED 状态<br/>(mFence = Acquire Fence)
    
    C->>BQ: acquireBuffer()
    BQ-->>C: 返回 Buffer & Acquire Fence
    Note over C: Slot 处于 ACQUIRED 状态<br/>Consumer 侧 GPU 等待 Acquire Fence<br/>信号到达后开始读取并合成

    C->>BQ: releaseBuffer(releaseFence)
    Note over BQ: Slot 恢复为 FREE 状态<br/>(mFence = Release Fence)
```

**关键点解析**：
1. **即时出队 (Immediate Dequeue)**：`FREE` 状态的 slot 随时可以被 dequeue。BufferQueue 不会阻塞等待 GPU 完成，而是直接将 `mFence` 作为 `outFence` 返回，由 Producer 侧的 GPU 负责异步等待。
2. **内容保护 (Content Protection)**：进入 `QUEUED` 后，Buffer 受 `acquireFence` 保护。虽然状态已变更，但 Consumer 在 fence signal 前绝不能读取像素。
3. **闭环 (Closed Loop)**：`ACQUIRED` 转换回 `FREE` 时，Consumer 生成的 `releaseFence` 被写入 slot，留给下一轮的 Producer 使用，从而形成完整的同步闭环。

---

## 四、实例分析：三缓冲管线满载运行

在 60fps 理想管线下，引入三缓冲机制是为了避免因 SF 正在持有 Buffer 而导致 App 无 Buffer 可用的阻塞问题。
下面通过一个交互式动画，演示 3 个 Slot (S0, S1, S2) 在 VSYNC 周期内的状态流转：

<details open>
<summary><b>点击查看/隐藏 60fps 状态机动态演示 (交互版)</b></summary>

<style>
.bq-widget { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #f8f9fa; border: 1px solid #e9ecef; border-radius: 12px; padding: 20px; max-width: 650px; margin: 20px 0; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
.bq-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 10px; }
.bq-header h3 { margin: 0; font-size: 18px; color: #343a40; font-weight: 600; }
.bq-controls { display: flex; gap: 8px; }
.bq-btn { background: #007bff; color: white; border: none; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; transition: background 0.2s; }
.bq-btn:hover { background: #0056b3; }
.bq-btn:disabled { background: #6c757d; cursor: not-allowed; opacity: 0.7; }
.bq-stage { display: flex; gap: 15px; margin-bottom: 20px; }
.bq-slot { flex: 1; border-radius: 8px; padding: 15px 10px; text-align: center; font-weight: bold; font-size: 16px; color: white; transition: all 0.3s ease; display: flex; flex-direction: column; gap: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.bq-slot span { font-size: 12px; font-weight: normal; opacity: 0.95; }
.st-free { background: #28a745; }
.st-dequeued { background: #17a2b8; }
.st-queued { background: #ffc107; color: #212529; }
.st-acquired { background: #dc3545; }
.bq-timeline { background: #fff; border-radius: 8px; padding: 15px; border: 1px solid #dee2e6; }
.bq-step-desc { font-size: 14px; color: #495057; line-height: 1.6; min-height: 48px; margin-bottom: 10px; font-weight: 500; }
.bq-progress { display: flex; align-items: center; justify-content: space-between; position: relative; margin-top: 15px; }
.bq-progress::before { content: ''; position: absolute; left: 10px; right: 10px; top: 50%; height: 2px; background: #dee2e6; z-index: 0; }
.bq-dot { width: 14px; height: 14px; border-radius: 50%; background: #dee2e6; z-index: 1; transition: all 0.3s ease; border: 2px solid #fff; box-shadow: 0 0 0 1px #dee2e6; }
.bq-dot.active { background: #007bff; box-shadow: 0 0 0 1px #007bff; transform: scale(1.2); }
</style>

<div class="bq-widget" id="bqWidget">
  <div class="bq-header">
    <h3>BufferQueue 三缓冲状态流转</h3>
    <div class="bq-controls">
      <button class="bq-btn" id="bqPrev" disabled>上一步</button>
      <button class="bq-btn" id="bqNext">下一步</button>
      <button class="bq-btn" id="bqReset">重置</button>
    </div>
  </div>
  
  <div class="bq-stage">
    <div class="bq-slot st-acquired" id="slot0">S0: ACQUIRED<span id="s0-owner">持有: Consumer (SF)</span></div>
    <div class="bq-slot st-free" id="slot1">S1: FREE<span id="s1-owner">持有: BufferQueue</span></div>
    <div class="bq-slot st-free" id="slot2">S2: FREE<span id="s2-owner">持有: BufferQueue</span></div>
  </div>
  
  <div class="bq-timeline">
    <div class="bq-step-desc" id="bqDesc"><b>V0 -> V1 期间</b>：SF 正在屏幕上展示前一帧 A，持有 S0。S1 和 S2 处于空闲状态。</div>
    <div class="bq-progress" id="bqProgress">
      <!-- Dots injected via script -->
    </div>
  </div>
</div>

<script>
(function() {
  const states = [
    {
      s0: { st: 'st-acquired', txt: 'ACQUIRED', owner: 'Consumer (SF)' },
      s1: { st: 'st-free', txt: 'FREE', owner: 'BufferQueue' },
      s2: { st: 'st-free', txt: 'FREE', owner: 'BufferQueue' },
      desc: '<b>V0 -> V1 期间</b>：SF 正在屏幕上展示前一帧 A，持有 S0。S1 和 S2 处于空闲状态。'
    },
    {
      s0: { st: 'st-acquired', txt: 'ACQUIRED', owner: 'Consumer (SF)' },
      s1: { st: 'st-dequeued', txt: 'DEQUEUED', owner: 'Producer (App)' },
      s2: { st: 'st-free', txt: 'FREE', owner: 'BufferQueue' },
      desc: '<b>V1 前</b>：App 调用 <code>dequeueBuffer()</code> 获取 S1 开始渲染新帧 B。'
    },
    {
      s0: { st: 'st-free', txt: 'FREE', owner: 'BufferQueue' },
      s1: { st: 'st-dequeued', txt: 'DEQUEUED', owner: 'Producer (App)' },
      s2: { st: 'st-free', txt: 'FREE', owner: 'BufferQueue' },
      desc: '<b>V1 触发</b>：SF 调用 <code>releaseBuffer()</code> 释放 S0。SF 尝试 acquire 新帧但队列为空，继续复用旧帧。'
    },
    {
      s0: { st: 'st-free', txt: 'FREE', owner: 'BufferQueue' },
      s1: { st: 'st-queued', txt: 'QUEUED', owner: 'BufferQueue' },
      s2: { st: 'st-free', txt: 'FREE', owner: 'BufferQueue' },
      desc: '<b>V1 -> V2 期间</b>：App 渲染帧 B 完成，调用 <code>queueBuffer()</code> 将 S1 入队。'
    },
    {
      s0: { st: 'st-free', txt: 'FREE', owner: 'BufferQueue' },
      s1: { st: 'st-queued', txt: 'QUEUED', owner: 'BufferQueue' },
      s2: { st: 'st-dequeued', txt: 'DEQUEUED', owner: 'Producer (App)' },
      desc: '<b>V1 -> V2 期间</b>：App 继续 <code>dequeueBuffer()</code> 获取 S2 开始渲染下一帧 C。'
    },
    {
      s0: { st: 'st-free', txt: 'FREE', owner: 'BufferQueue' },
      s1: { st: 'st-acquired', txt: 'ACQUIRED', owner: 'Consumer (SF)' },
      s2: { st: 'st-dequeued', txt: 'DEQUEUED', owner: 'Producer (App)' },
      desc: '<b>V2 触发</b>：SF 收到 Vsync，调用 <code>acquireBuffer()</code> 消费入队的 S1（帧 B）。'
    },
    {
      s0: { st: 'st-free', txt: 'FREE', owner: 'BufferQueue' },
      s1: { st: 'st-acquired', txt: 'ACQUIRED', owner: 'Consumer (SF)' },
      s2: { st: 'st-queued', txt: 'QUEUED', owner: 'BufferQueue' },
      desc: '<b>V2 -> V3 期间</b>：App 渲染帧 C 完成，将 S2 <code>queueBuffer()</code> 入队。'
    },
    {
      s0: { st: 'st-dequeued', txt: 'DEQUEUED', owner: 'Producer (App)' },
      s1: { st: 'st-acquired', txt: 'ACQUIRED', owner: 'Consumer (SF)' },
      s2: { st: 'st-queued', txt: 'QUEUED', owner: 'BufferQueue' },
      desc: '<b>稳态满载</b>：App 获取 S0 渲染帧 D。<br/>此时 3 个 Slot 各司其职：S1 在显示 (ACQUIRED)，S2 在排队 (QUEUED)，S0 在渲染 (DEQUEUED)。这是三缓冲满负荷运行的标准快照。'
    }
  ];

  let currentStep = 0;
  
  const s0 = document.getElementById('slot0');
  const s1 = document.getElementById('slot1');
  const s2 = document.getElementById('slot2');
  const o0 = document.getElementById('s0-owner');
  const o1 = document.getElementById('s1-owner');
  const o2 = document.getElementById('s2-owner');
  const desc = document.getElementById('bqDesc');
  const btnNext = document.getElementById('bqNext');
  const btnPrev = document.getElementById('bqPrev');
  const btnReset = document.getElementById('bqReset');
  const progress = document.getElementById('bqProgress');

  if(progress && progress.children.length === 0) {
    states.forEach((_, i) => {
      const dot = document.createElement('div');
      dot.className = 'bq-dot' + (i === 0 ? ' active' : '');
      dot.id = 'dot' + i;
      progress.appendChild(dot);
    });
  }

  function updateState() {
    const s = states[currentStep];
    
    s0.className = 'bq-slot ' + s.s0.st;
    s0.childNodes[0].nodeValue = 'S0: ' + s.s0.txt;
    o0.innerText = '持有: ' + s.s0.owner;
    
    s1.className = 'bq-slot ' + s.s1.st;
    s1.childNodes[0].nodeValue = 'S1: ' + s.s1.txt;
    o1.innerText = '持有: ' + s.s1.owner;
    
    s2.className = 'bq-slot ' + s.s2.st;
    s2.childNodes[0].nodeValue = 'S2: ' + s.s2.txt;
    o2.innerText = '持有: ' + s.s2.owner;
    
    desc.innerHTML = s.desc;
    
    for(let i=0; i<states.length; i++) {
      const d = document.getElementById('dot'+i);
      if(d) d.className = 'bq-dot' + (i <= currentStep ? ' active' : '');
    }
    
    if(btnPrev) btnPrev.disabled = (currentStep === 0);
    if(btnNext) btnNext.disabled = (currentStep === states.length - 1);
  }

  if(btnNext) btnNext.onclick = () => { if (currentStep < states.length - 1) { currentStep++; updateState(); } };
  if(btnPrev) btnPrev.onclick = () => { if (currentStep > 0) { currentStep--; updateState(); } };
  if(btnReset) btnReset.onclick = () => { currentStep = 0; updateState(); };

})();
</script>
</details>

> **结论**：在三缓冲下，同时出现 `ACQUIRED × 1 + QUEUED × 1 + DEQUEUED × 1` 是系统吞吐量达到最高的**正常满载状态**。只有当 App 试图在 `FREE` 数量为 0 时调用 `dequeueBuffer()`，才会触发 `tooManyBuffers` 错误并导致短暂阻塞。
