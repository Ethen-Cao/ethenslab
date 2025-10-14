+++
date = '2025-09-29T10:22:54+08:00'
draft = false
title = 'Activity 跨屏幕迁移'
+++


![](/ethenslab/static/images/activity-reparent.png)

## 分步说明（与生命周期映射）

1. **Launcher 发起**：用户点击 → Launcher 构造 `Intent`（带 `launchDisplayId=2`）并调用 `startActivity()` 到 ATMS。
2. **ATMS 决策**：ATMS 在 system_server 内部查看 `ActivityRecord/TaskRecord`，决定把某个 Task 从 Display1 移到 Display2（修改 parent：`TaskDisplayArea`）。这一步只是服务端的数据结构变化，不会直接调用应用对象的方法。
3. **协调 WMS**：ATMS 通知 WMS 准备窗口切换（应用 transition），以便在 surface 层面上能做平滑迁移。
4. **暂停目标 Display 上的当前前台**（ActivityB）：为了保证目标 Display 上只会有一个 resumed Activity，ATMS 先对 Display2 上当前的前台 Activity（ActivityB）发 `IApplicationThread.schedulePauseActivity`，等待应用进程回 ACK（pauseFinished）。
5. **暂停将要被移动的 ActivityA（源 Display1）**：ATMS 对 ActivityA 发 `schedulePauseActivity`，应用进程进入 `onPause()`，并回 ACK。

   * 这一步非常重要：把要移动的 Activity 保持在非-resumed 状态，便于改变它的窗口所属 Display/Surface。
6. **WMS 做 Window/Surface reparent**：ATMS 请求 WMS 将对应的 `WindowContainer`/task 窗口树从 Display1 移到 Display2；WMS 在 SurfaceControl 层（通过 SurfaceFlinger）把 layer 重新 attach 到目标 Display 的 layer stack。
7. **配置变化处理**：如果 reparent 后显示参数（DPI/大小/方向）发生变化，ATMS 可能对 ActivityA 发 `scheduleRelaunchActivity`（系统请求 Activity 重启或调用 onConfigurationChanged），这可能导致 `onDestroy()`→`onCreate()` 的重建路径，或仅触发 `onConfigurationChanged()`（取决于 Activity 是否声明可处理配置变化）。
8. **恢复 ActivityA（在 Display2）**：在 Surface 已就位且（必要时）完成 relaunch 后，ATMS 发 `scheduleResumeActivity` 让 ActivityA 进入 `onResume()`，成为 Display2 的前台 resumed Activity。
9. **恢复源 Display 的新栈顶（ActivityX）**：源 Display1 的栈顶发生变化，ATMS 会对新的栈顶 ActivityX 发 `scheduleResumeActivity` 让它 `onResume()`，成为 Display1 的前台。
10. **更新内部状态**：ATMS 更新每个 Display 的 `mTopResumedActivity` 等内部状态，结束迁移流程。

---

## 注意的变体与细节

* **同进程 vs 跨进程**

  * 如果 ActivityA、ActivityB、ActivityX 在同一 app 进程（同一 `ActivityThread`），这些 `scheduleXxxActivity` 变成对同一进程的方法调用，系统会尽量合并/顺序化这些调用以避免重复/冲突。不同进程时，pause/ack 的等待更明显（Binder 往返）。
* **是否重建（recreate）**

  * 若目标 Display 与源 Display 在配置上差别很小，系统可能只发 `onConfigurationChanged()`。若差别较大（例如密度或多窗口相关资源不同），系统会 `scheduleRelaunchActivity`，走 destroy→create 流程。
* **顺序保障**

  * 为了避免同时出现多个 resumed Activity，ATMS 会先 pause 要离开的/被覆盖的 Activity（并等 ack），再 resume 新的 Activity（或等待 WMS 的 surface reparent 完成后 resume）。具体实现会在 `ActivityStarter` / `ActivityTaskManagerService` 中做状态机控制并使用超时/回滚策略。
* **视觉连续性**

  * WMS 在 reparent 时会尽量通过动画/transaction 保持视觉连续（比如先把窗口设为不可见或放入正在转换的 layer，然后在目标 Display 上 reveal），以减少闪烁。

---

## 简短结论（归纳）

* **ATMS 只在 system_server 修改服务端对象（ActivityRecord/TaskRecord）并决定 reparent；它不会直接“对 Activity 对象下命令”**。
* **真正的生命周期回调发生在应用进程（ActivityThread）——由 ATMS 通过 IApplicationThread（Binder）发起 schedulePause/scheduleResume/scheduleRelaunch 等调用来驱动**。
* **WMS 负责窗口树与 Surface 的实际迁移并与 SurfaceFlinger 协作，保证显示层面的正确性与平滑过渡**。
* 在 reparent 过程中，源 Display 和目标 Display 上的 Activity 会依次经历 pause/stop/resume（或在必要时重新创建），系统通过 pause-ack、reparentComplete 等同步点来保证有序与一致性。

---