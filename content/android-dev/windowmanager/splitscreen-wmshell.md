+++
date = '2025-09-29T10:22:54+08:00'
draft = false
title = 'SplitScreenController flow'
+++

## 时序图

![](/ethenslab/images/splitscreen_wmshell.png)

## Debug

1. 打印分屏区域

    ```shell
    adb shell dumpsys activity service SystemUIService WMShell
    ```

2. dump SystemUI
   ```shell
   $ adb shell dumpsys activity service SystemUIService
   ```

3. Enable protolog
   
   参考 `frameworks/base/libs/WindowManager/Shell/src/com/android/wm/shell/ProtoLogController.java`:

   * 查看protolog status：
   ```shell
    $ adb shell dumpsys activity service SystemUIService WMShell protolog status
    SERVICE com.android.systemui/.SystemUIService e73cb38 pid=4871 user=0
    Client:

        com.android.systemui.wmshell.WMShell:
        ----------------------------------------------------------------------------
        ProtoLog status: Disabled
        Enabled log groups: 
        Proto: TEST_GROUP WM_DEBUG_ADD_REMOVE WM_DEBUG_ANIM WM_DEBUG_APP_TRANSITIONS WM_DEBUG_APP_TRANSITIONS_ANIM WM_DEBUG_BACK_PREVIEW WM_DEBUG_BOOT WM_DEBUG_CONFIGURATION WM_DEBUG_CONTAINERS WM_DEBUG_CONTENT_RECORDING WM_DEBUG_DRAW WM_DEBUG_DREAM WM_DEBUG_FOCUS WM_DEBUG_FOCUS_LIGHT WM_DEBUG_IME WM_DEBUG_IMMERSIVE WM_DEBUG_KEEP_SCREEN_ON WM_DEBUG_LOCKTASK WM_DEBUG_ORIENTATION WM_DEBUG_RECENTS_ANIMATIONS WM_DEBUG_REMOTE_ANIMATIONS WM_DEBUG_RESIZE WM_DEBUG_SCREEN_ON WM_DEBUG_STARTING_WINDOW WM_DEBUG_STATES WM_DEBUG_SWITCH WM_DEBUG_SYNC_ENGINE WM_DEBUG_TASKS WM_DEBUG_WALLPAPER WM_DEBUG_WINDOW_INSETS WM_DEBUG_WINDOW_MOVEMENT WM_DEBUG_WINDOW_ORGANIZER WM_DEBUG_WINDOW_TRANSITIONS WM_DEBUG_WINDOW_TRANSITIONS_MIN WM_ERROR WM_SHELL_BACK_PREVIEW WM_SHELL_DESKTOP_MODE WM_SHELL_DRAG_AND_DROP WM_SHELL_FLOATING_APPS WM_SHELL_FOLDABLE WM_SHELL_INIT WM_SHELL_PICTURE_IN_PICTURE WM_SHELL_RECENTS_TRANSITION WM_SHELL_RECENT_TASKS WM_SHELL_SPLIT_SCREEN WM_SHELL_STARTING_WINDOW WM_SHELL_SYSUI_EVENTS WM_SHELL_TASK_ORG WM_SHELL_TRANSITIONS WM_SHOW_SURFACE_ALLOC WM_SHOW_TRANSACTIONS
        Logcat: WM_DEBUG_BACK_PREVIEW WM_DEBUG_CONTENT_RECORDING WM_DEBUG_DREAM WM_DEBUG_WINDOW_TRANSITIONS_MIN WM_ERROR WM_SHELL_BACK_PREVIEW WM_SHELL_DRAG_AND_DROP WM_SHELL_INIT WM_SHELL_PICTURE_IN_PICTURE WM_SHELL_RECENTS_TRANSITION WM_SHELL_SPLIT_SCREEN WM_SHELL_TRANSITIONS
        Logging definitions loaded: 0

        Dump took 2ms
    ```

    * enable protolog：
    ```shell
    $ adb shell dumpsys activity service SystemUIService WMShell protolog enable WM_SHELL_TRANSITIONS WM_SHELL_DRAG_AND_DROP WM_SHELL_SPLIT_SCREEN
    $ adb shell dumpsys activity service SystemUIService WMShell protolog start
    ```


