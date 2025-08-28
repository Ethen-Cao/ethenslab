+++
date = '2025-08-27T11:36:11+08:00'
draft = false
title = 'Android log机制'
+++

![](/ethenslab/images/android-eventlog.png)

### 架構圖詳解

1.  **日誌寫入路徑 (Write Path)**

      * **起點**: 應用程式或 Android 框架服務 (如 `ActivityManagerService`) 調用 `android.util.EventLog.writeEvent()`。
      * **轉換**: 呼叫通過 JNI 進入原生層，由 `liblog.so` 這個 C/C++ 函式庫接管。
      * **通信接口**: `liblog` 通過一個名為 `/dev/socket/logdw` (logd writer) 的 UNIX Domain Socket，將事件日誌以高效的二進位格式 (`logger_entry` 結構) 發送給 `logd` 守護進程。這是一個單向的寫入操作。

2.  **`logd` 內部實現 (Log Daemon Internals)**

      * **Socket Listener**: `logd` 內部有一個專門的線程，負責監聽 `/dev/socket/logdw` 接口，接收來自系統中所有進程的日誌數據。
      * **Ring Buffers**: 接收到的日誌會被分門別類地存入對應的**內存中環形緩衝區 (In-Memory Ring Buffers)**。對於 EventLog，數據被寫入名為 `events` 的緩衝區。這是一個高效的內存數據結構，當寫滿時會自動覆蓋最舊的紀錄。
      * **Command Listener**: `logd` 同時也監聽另一個 Socket `/dev/socket/logdr` (logd reader)，用於接收來自 `logcat` 等客戶端的讀取指令。

3.  **日誌讀取與解析路徑 (Read & Parse Path)**

      * **客戶端請求**: 當您執行 `adb logcat -b events` 時，`logcat` 進程會連接到 `/dev/socket/logdr`。
      * **通信接口**: `logcat` 向 `logd` 發送指令，要求讀取 `events` 緩衝區的內容。
      * **數據回傳**: `logd` 的 `Command Listener` 收到指令後，從 `Ring Buffers` 中提取 `events` 的二進位日誌數據，並通過同一個 Socket 流式傳回給 `logcat`。
      * **解析與翻譯 (關鍵步驟)**:
          * `logcat` 收到的是純二進位數據流。
          * 為了將其變為可讀文本，`logcat` 會打開並解析 `/system/etc/event-log-tags` 文件。
          * 該文件定義了整數 `tag` 與其對應的事件名稱、參數類型的映射關係。
          * `logcat` 利用這個映射表，將二進位流 "翻譯" 成我們在終端機上看到的人類可讀的格式，然後輸出。
