+++
date = '2025-09-27T17:17:50+08:00'
draft = true
title = ''
+++

### 📂 Polaris 1.0 工程目录全景图

**ROOT**: `vendor/voyah/system/polaris/`

```text
vendor/voyah/polaris/
├── Android.bp                      // [构建] 根构建脚本，聚合下级模块
├── README.md                       // [文档] 项目说明与编译指南
│
├── protocol/                       // 【模块1】协议规范与代码生成 (Protocol)
│   ├── registry/
│   │   └── global_events.csv       // [核心资产] 全局事件注册表
│   ├── scripts/
│   │   ├── codegen.py              // [脚本] 自动生成 EventID.java 和 polaris_event.h
│   │   └── requirements.txt        // [依赖] python 依赖库
│   └── templates/                  // [模板] 代码生成模板 (Jinja2)
│       └── EventID.java.tmpl
│
├── sdk/                            // 【模块2】公共框架库 (Library)
│   ├── Android.bp                  // [构建] 生成 "polaris-framework.jar"
│   ├── src/main/aidl/              // [IPC] AIDL 接口定义
│   │   └── com/voyah/polaris/
│   │       └── IPolarisAgentService.aidl  // oneway 接口：void reportEvent(in PolarisEvent event)
│   │
│   └── src/main/java/com/voyah/polaris/
│       ├── PolarisAgentManager.java    // [入口] 给 SystemServer/App 用的单例 Client
│       ├── PolarisConstant.java        // [常量] 通用配置 (如 Service Package Name)
│       │
│       ├── event/                      // [数据域] 事件实体
│       │   ├── PolarisEvent.java       // [核心] 通用事件容器 (Parcelable + Bundle)
│       │   └── EventID.java            // [自动生成] 事件 ID 常量池
│       │
│       └── utils/                      // [工具] SDK 内部工具
│           └── RateLimiter.java        // [流控] 客户端限流器
│
├── app/                            // 【模块3】服务端应用 (Android App)
│   ├── Android.bp                  // [构建] 生成 "PolarisAgent.apk"
│   ├── AndroidManifest.xml         // [清单] 声明 android:sharedUserId="android.uid.system"
│   ├── res/                        // [资源] 布局与图标
│   │
│   └── src/main/java/com/voyah/polaris/agent/ // [私有] App 内部实现
│       ├── PolarisAgentApplication.java // App 生命周期管理
│       ├── PolarisAgentService.java     // [Service] 核心服务 (Stub 实现)
│       │
│       ├── core/                        // [核心业务]
│       │   ├── EventProcessor.java      // [调度] 内存队列 -> 数据库 -> 上传
│       │   ├── NativeReceiver.java      // [通信] 监听 Native Daemon (LocalSocket)
│       │   └── VlmUploader.java         // [上报] 调用车云 SDK (Java 接口)
│       │
│       ├── monitor/                     // [监控源] 外部事件监听
│       │   ├── DropBoxMonitor.java      // [DropBox] 监听系统 Crash/ANR 广播
│       │   └── DropBoxParser.java       // [解析] 文本解析映射为 Event
│       │
│       ├── db/                          // [存储] SQLite 数据库
│       │   ├── PolarisDbHelper.java
│       │   └── EventDao.java            // 批量写入与查询
│       │
│       └── usb/                         // [导出] USB 数据导出
│           └── UsbExporter.java         // 监听挂载广播，执行 DB Dump
│
└── native/                         // 【模块4】底层守护进程 (Native Daemon)
    ├── Android.bp                  // [构建] 生成 "polaris_native_daemon"
    ├── main.cpp                    // [入口] 守护进程启动
    ├── include/
    │   ├── polaris_protocol.h      // [协议] VSOCK & LocalSocket 数据结构定义
    │   └── polaris_event.h         // [自动生成] C++ 事件 ID 常量
    └── src/
        ├── VsockListener.cpp       // [通信] 监听 Linux Host 消息
        ├── EventCache.cpp          // [缓存] 环形队列 (App Crash 时暂存数据)
        └── SocketDispatcher.cpp    // [分发] 发送数据给 Android App

```

---

### 🔑 关键文件代码预览

这里提供几个 **关键节点文件** 的核心代码片段。

#### 1. `sdk/src/main/aidl/com/voyah/polaris/IPolarisAgentService.aidl`

```java
// IPolarisAgentService.aidl
package com.voyah.polaris;

import com.voyah.polaris.event.PolarisEvent;

interface IPolarisAgentService {
    /**
     * Report an event to Polaris Agent.
     * Must be oneway to prevent blocking the caller (e.g., SystemServer).
     */
    oneway void reportEvent(in PolarisEvent event);
}

```

#### 2. `sdk/src/main/java/com/voyah/polaris/event/PolarisEvent.java`

```java
package com.voyah.polaris.event;

import android.os.Bundle;
import android.os.Parcel;
import android.os.Parcelable;

/**
 * Universal Event Container.
 */
public class PolarisEvent implements Parcelable {
    public long eventId;
    public long timestamp;
    public int pid;
    public String processName;
    public Bundle params;       // Business payload (key-value)
    public String logFilePath;  // Attachment path

    public PolarisEvent(long eventId) {
        this.eventId = eventId;
        this.timestamp = System.currentTimeMillis();
        this.params = new Bundle();
    }
    // ... Parcelable implementation ...
}

```

#### 3. `sdk/Android.bp` (构建脚本)

```groovy
java_library {
    name: "polaris-framework",
    installable: true,
    
    srcs: [
        "src/main/java/**/*.java",
        "src/main/aidl/**/*.aidl",
    ],
    
    // 如果你在做 Framework 开发，通常不需要 sdk_version
    // 如果是独立 App 开发，可以用 "system_current"
    platform_apis: true, 
}

```

#### 4. `app/src/main/java/com/voyah/polaris/agent/monitor/DropBoxMonitor.java`

```java
package com.voyah.polaris.agent.monitor;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.DropBoxManager;
import com.voyah.polaris.event.EventID;
// ...

public class DropBoxMonitor extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (DropBoxManager.ACTION_DROPBOX_ENTRY_ADDED.equals(intent.getAction())) {
            String tag = intent.getStringExtra(DropBoxManager.EXTRA_TAG);
            long time = intent.getLongExtra(DropBoxManager.EXTRA_TIME, 0);
            
            // 将 Tag 映射为 Polaris Event ID
            long eventId = mapTagToId(tag);
            if (eventId != -1) {
                // 启动异步任务处理日志
                EventProcessor.getInstance().processDropBoxAsync(tag, time, eventId);
            }
        }
    }
    
    private long mapTagToId(String tag) {
        if ("system_server_anr".equals(tag)) return EventID.GVM_SYS_FW_ANR;
        if ("system_server_crash".equals(tag)) return EventID.GVM_SYS_FW_CRASH;
        // ...
        return -1;
    }
}

```
