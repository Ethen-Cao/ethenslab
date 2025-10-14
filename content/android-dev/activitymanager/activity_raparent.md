
当 `startActivity` 请求将一个已存在于主屏的 `Activity` 移动到副屏时，核心决策发生在 `ActivityStarter` 的 `setTargetRootTaskIfNeeded` 方法中。该方法会直接调用 `Task.reparent()` 来执行跨屏迁移。由于继承关系，这个调用最终会执行 `WindowContainer.reparent()` 方法，该方法是整个转场动画和窗口层级变更的真正起点，它在内部**直接调用 `onDisplayChanged`**，并将变更以递归方式通知到目标 `ActivityRecord`。

### 从 `startActivity` 到 `onDisplayChanged` 的精确流程与调用堆栈

#### 阶段一：ActivityTaskManagerService & ActivityStarter - 决策与指令发起

此阶段在 `system_server` 的 ATMS 线程中进行，`ActivityStarter` 是核心决策者。

1.  **入口: `ActivityTaskManagerService.startActivity()`**

      * 用户或应用发起 `startActivity` 请求，通过 Binder 调用进入 `ActivityTaskManagerService`。
      * ATMS 将请求委托给一个 `ActivityStarter` 实例来处理。

2.  **`ActivityStarter.execute()` -> `startActivityUnchecked()` -> `startActivityInner()`**

      * 这是所有 Activity 启动请求的统一处理流程。
      * 在 `startActivityInner()` 内部，系统会调用 `getReusableTask()` 来寻找一个可以重用的、已存在的 `Task`。在您的场景中，这一步会成功找到 `MainActivity` 所在的 `Task`。
      * 因为找到了 `reusedTask`，流程会进入 `recycleTask()` 方法。

3.  **`ActivityStarter.recycleTask()` -> `setTargetRootTaskIfNeeded()`: 做出 `reparent` 决策**

      * 在 `recycleTask()` 方法中，它会调用 `setTargetRootTaskIfNeeded()` 来最终确定和调整 `Activity` 所在的 `Task` 的位置。
      * `setTargetRootTaskIfNeeded()` 方法会检查 `ActivityOptions` 中是否指定了 `launchDisplayId`，并据此找到或创建位于目标 Display 上的 `mTargetRootTask`。
      * 当它发现 `Activity` 当前所在的 `Task` (`intentTask`) 并不在目标 `mTargetRootTask` 的层级下时（即跨屏），它就会调用 `Task.reparent()` 来执行移动。
      * **关键源码佐证 (`ActivityStarter.java` 的 `setTargetRootTaskIfNeeded` 方法)**:
        ```java
        private void setTargetRootTaskIfNeeded(ActivityRecord intentActivity) {
            // ...
            Task intentTask = intentActivity.getTask();
            // ...
            // mTargetRootTask 会被设置为位于新 Display (如 display 3) 上的 Root Task
            mTargetRootTask = getOrCreateRootTask(...);
            // ...

            // 检查 intentActivity 是否已经在目标层级下
            if (intentActivity.isDescendantOf(mTargetRootTask)) {
                // ...
            } else if (intentActivity.getWindowingMode() != WINDOWING_MODE_PINNED) {
                // 决策：需要移动 Task。直接调用 Task.reparent()
                intentTask.reparent(mTargetRootTask, ON_TOP, REPARENT_MOVE_ROOT_TASK_TO_FRONT,
                        ANIMATE, DEFER_RESUME, "reparentToTargetRootTask");
                mMovedToFront = true;
            }
        }
        ```
      * **此阶段堆栈**:
        ```
        com.android.server.wm.Task.reparent(Task.java:...)
        com.android.server.wm.ActivityStarter.setTargetRootTaskIfNeeded(ActivityStarter.java:...)
        com.android.server.wm.ActivityStarter.recycleTask(ActivityStarter.java:...)
        com.android.server.wm.ActivityStarter.startActivityInner(ActivityStarter.java:...)
        com.android.server.wm.ActivityStarter.startActivityUnchecked(ActivityStarter.java:...)
        com.android.server.wm.ActivityStarter.execute(ActivityStarter.java:...)
        com.android.server.wm.ActivityTaskManagerService.startActivity(ActivityTaskManagerService.java:...)
        ... (Binder call from App)
        ```

#### 阶段二：WindowContainer 层级 - 执行 `reparent` 并通知变更

此阶段由 `ActivityStarter` 的调用触发，进入了 WMS 核心数据结构的变更流程。

1.  **`Task.reparent()` -> `WindowContainer.reparent()`**

      * `Task.reparent(Task, ...)` 被调用。
      * 在 `Task.java` 内部，这个方法会调用其另一个重载方法 `reparent(newParent, position)`。
      * 由于 `Task` 继承自 `TaskFragment`，而 `TaskFragment` 继承自 `WindowContainer`，因此该调用会**直接解析到 `WindowContainer.java` 中的 `reparent(WindowContainer, int)` 方法**。

2.  **`WindowContainer.reparent()`: 转场动画的起点与变更的执行**

      * 这是整个 `reparent` 和动画流程的核心。它负责发起动画、变更层级并触发通知。
      * **关键源码佐证 (`WindowContainer.java`)**:
        ```java
        void reparent(WindowContainer newParent, int position) {
            // ...
            // 1. 发起转场请求，创建 mCollectingTransition
            mTransitionController.collectReparentChange(this, newParent);

            // ...
            final DisplayContent prevDc = oldParent.getDisplayContent();
            final DisplayContent dc = newParent.getDisplayContent();

            // 2. 执行实际的父子关系变更 (removeChild / addChild)
            oldParent.removeChild(this);
            newParent.addChild(this, position);

            // ...
            if (prevDc != dc) {
                // 3. 直接调用 onDisplayChanged，启动递归通知
                onDisplayChanged(dc);
                prevDc.setLayoutNeeded();
            }
            // ...
            // 4. 在 onDisplayChanged 之后，才调用 onParentChanged
            onParentChanged(newParent, oldParent);
        }
        ```

3.  **`onDisplayChanged()` 的递归调用**

      * `WindowContainer.reparent()` 在检测到 `DisplayContent` 发生变化后，**直接调用** `onDisplayChanged()`。
      * 该调用会从被 `reparent` 的 `Task` 开始，递归地向下传递给它的所有子容器。

4.  **到达最终目标: `ActivityRecord.onDisplayChanged()`**

      * `Task.onDisplayChanged()` 会遍历其下的 `ActivityRecord` 并调用它们的 `onDisplayChanged()` 方法。
      * **最终的完整堆栈**:
        ```
        // 这是 ActivityRecord.onDisplayChanged() 被调用时的完整堆栈
        com.android.server.wm.ActivityRecord.onDisplayChanged(ActivityRecord.java:...)
        com.android.server.wm.WindowContainer.onDisplayChanged(WindowContainer.java:...)  // ActivityRecord 的 super.onDisplayChanged
        com.android.server.wm.Task.onDisplayChanged(Task.java:...)                      // Task 分发给 ActivityRecord
        // 注意：onDisplayChanged 是被 reparent 直接调用的，而不是 onParentChanged
        com.android.server.wm.WindowContainer.reparent(WindowContainer.java:...)           // reparent 流程的起点
        com.android.server.wm.Task.reparent(Task.java:...)                                   // 继承链调用
        com.android.server.wm.ActivityStarter.setTargetRootTaskIfNeeded(ActivityStarter.java:...)
        com.android.server.wm.ActivityStarter.recycleTask(ActivityStarter.java:...)
        com.android.server.wm.ActivityStarter.startActivityInner(ActivityStarter.java:...)
        com.android.server.wm.ActivityStarter.startActivityUnchecked(ActivityStarter.java:...)
        com.android.server.wm.ActivityStarter.execute(ActivityStarter.java:...)
        com.android.server.wm.ActivityTaskManagerService.startActivity(ActivityTaskManagerService.java:...)
        ... (Binder call from App)
        ```
5. **WindowContainer.onParentChanged 触发 ActivityRecord.onConfigurationChanged**
   WindowContainer继承自 ConfigurationContainer,在`WindowContainer.reparent()`中调用onParentChanged:
   ```
   WindowContainer.reparent() 
    -> WindowContainer.onParentChanged() 
        -> super.onParentChanged 
            -> ConfigurationContainer.onParentChanged() 
                -> ConfigurationContainer.onConfigurationChanged() 
                    -> child.onConfigurationChanged 
                        -> ActivityRecord.onConfigurationChanged()
    ```

#### Relaunching ActivityRecord

    当configuration改变后，在ActivityRecord visible更新的过程中，会触发relaunch。
    ```
    Moving to RESUMED Relaunching ActivityRecord{f40f734 u0 com.example.test/.MainActivity} t113} callers=
    com.android.server.wm.ActivityRecord.ensureActivityConfiguration:9479 
    com.android.server.wm.ActivityRecord.ensureActivityConfiguration:9310 
    com.android.server.wm.EnsureActivitiesVisibleHelper.setActivityVisibilityState:191 
    com.android.server.wm.EnsureActivitiesVisibleHelper.process:144 
    com.android.server.wm.TaskFragment.updateActivityVisibilities:1165 
    com.android.server.wm.Task.lambda$ensureActivitiesVisible$19:4895
    ```

    下面是 Task.java的 `ensureActivitiesVisible` 实现

    ```java
        /**
     * Ensure visibility with an option to also update the configuration of visible activities.
     * @see #ensureActivitiesVisible(ActivityRecord, int, boolean)
     * @see RootWindowContainer#ensureActivitiesVisible(ActivityRecord, int, boolean)
     * @param starting The top most activity in the task.
     *                 The activity is either starting or resuming.
     *                 Caller should ensure starting activity is visible.
     * @param notifyClients Flag indicating whether the visibility updates should be sent to the
     *                      clients in {@link EnsureActivitiesVisibleHelper}.
     * @param preserveWindows Flag indicating whether windows should be preserved when updating
     *                        configuration in {@link EnsureActivitiesVisibleHelper}.
     * @param configChanges Parts of the configuration that changed for this activity for evaluating
     *                      if the screen should be frozen as part of
     *                      {@link EnsureActivitiesVisibleHelper}.
     */
    // TODO: Should be re-worked based on the fact that each task as a root task in most cases.
    void ensureActivitiesVisible(@Nullable ActivityRecord starting, int configChanges,
            boolean preserveWindows, boolean notifyClients) {
        mTaskSupervisor.beginActivityVisibilityUpdate();
        try {
            forAllLeafTasks(task -> {
                task.updateActivityVisibilities(starting, configChanges, preserveWindows,
                        notifyClients);
            }, true /* traverseTopToBottom */);

            if (mTranslucentActivityWaiting != null &&
                    mUndrawnActivitiesBelowTopTranslucent.isEmpty()) {
                // Nothing is getting drawn or everything was already visible, don't wait for
                // timeout.
                notifyActivityDrawnLocked(null);
            }
        } finally {
            mTaskSupervisor.endActivityVisibilityUpdate();
        }
    }
    ```

    在ensureActivityConfiguration中就会调用relaunchActivityLocked：
    ```
    ActivityRecord.ensureActivityConfiguration：
        -> ActivityRecord.relaunchActivityLocked 
            -> ActivityRecord.startFreezingScreenLocked
    ```
