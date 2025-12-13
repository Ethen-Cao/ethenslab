+++
date = '2025-08-27T11:36:11+08:00'
draft = false
title = 'Protocol Buffers (Protobuf) 技术指南'
+++

## 1. 简介

**Protocol Buffers** (简称 Protobuf) 是 Google 开发的一种语言无关、平台无关、可扩展的**序列化结构数据**的机制。

相比于 XML 和 JSON，Protobuf 的主要特点是：

  * **体积更小**：二进制格式，数据紧凑。
  * **速度更快**：解析和序列化速度极快。
  * **强类型**：通过 `.proto` 文件定义数据结构，编译时自动生成代码。
  * **兼容性**：良好的向后兼容性支持。

在 Android 系统中，Protobuf 被广泛用于 StatsD (指标上报)、Incidentd (事故报告)、Binder IPC 数据传输等场景。

-----

## 2. 工作流程与架构

Protobuf 的核心工作流分为：**定义**、**编译**、**使用**、**序列化/反序列化**。

![](/ethenslab/images/Protobuf.png)

-----

## 3. 语法指南 (.proto)

目前主流版本为 **proto3**。以下是一个典型的 `.proto` 文件示例。

### 3.1 基础结构

创建一个名为 `car_event.proto` 的文件：

```protobuf
// 1. 指定语法版本 (必须)
syntax = "proto3";

// 2. 定义包名 (防止命名冲突)
package com.example.cockpit;

// 3. 配置生成选项 (Java相关)
option java_package = "com.example.cockpit.proto"; // 生成的Java包路径
option java_outer_classname = "CarEventProto";   // 生成的Java外层类名

// 4. 定义消息 (Message)
message VehicleStatus {
    // 字段格式: 类型 字段名 = 字段编号;
    
    // 标量类型
    int32 speed = 1;          // 整数
    string vin_code = 2;      // 字符串
    bool is_moving = 3;       // 布尔值
    
    // 枚举类型
    enum Gear {
        GEAR_UNKNOWN = 0; // proto3 枚举第一个值必须为0
        GEAR_P = 1;
        GEAR_R = 2;
        GEAR_N = 3;
        GEAR_D = 4;
    }
    Gear current_gear = 4;

    // 嵌套消息
    EngineInfo engine = 5;

    // 数组 (Repeated)
    repeated string error_codes = 6; // 相当于 List<String>
}

message EngineInfo {
    float rpm = 1;
    float temperature = 2;
}
```

### 3.2 关键概念

1.  **字段编号 (Field Number)**：例如 `speed = 1` 中的 `1`。
      * **非常重要**：这是二进制数据中字段的唯一标识，而不是字段名。
      * 一旦数据投入使用，**绝对不能修改**已存在字段的编号。
      * 1\~15 占用 1 个字节，16\~2047 占用 2 个字节（建议将频繁使用的字段放在 1\~15）。
2.  **类型映射**：
      * `int32/int64` -\> Java `int/long`, C++ `int32_t/int64_t`
      * `string` -\> Java `String`, C++ `std::string`
      * `bool` -\> Java `boolean`, C++ `bool`

-----

## 4. 编译方法

将 `.proto` 文件转换为目标语言代码。

### 4.1 使用标准 protoc 编译

Google 提供的标准编译器。

**编译为 Java 代码:**

```bash
protoc --java_out=./src/main/java car_event.proto
```

**编译为 C++ 代码:**

```bash
# 会生成 .pb.h 和 .pb.cc 文件
protoc --cpp_out=./src/main/cpp car_event.proto
```

### 4.2 在 Android 构建系统中编译 (Android.bp)

Android 源码环境通常使用 `Android.bp` 自动处理。

```go
java_library {
    name: "car-event-proto-java",
    proto: {
        type: "lite", // 推荐移动端使用 lite 版本，体积更小
    },
    srcs: ["src/proto/car_event.proto"],
    sdk_version: "current",
}

cc_library {
    name: "libcarevent_proto",
    proto: {
        type: "lite",
        export_proto_headers: true,
    },
    srcs: ["src/proto/car_event.proto"],
}
```

-----

## 5. 代码使用示例

### 5.1 Java 侧使用 (序列化与反序列化)

Protobuf 使用 **Builder 模式** 来构建对象。

```java
import com.example.cockpit.proto.CarEventProto.VehicleStatus;
import com.example.cockpit.proto.CarEventProto.VehicleStatus.Gear;

// 1. 构建对象 (序列化前)
VehicleStatus status = VehicleStatus.newBuilder()
    .setSpeed(120)
    .setVinCode("example12345678")
    .setIsMoving(true)
    .setCurrentGear(Gear.GEAR_D)
    .addErrorCodes("E001") // 添加数组元素
    .addErrorCodes("E002")
    .build();

// 2. 序列化 (转为 byte[])
// 场景：通过 Socket 发送、存入文件、存入 StatsD
byte[] data = status.toByteArray(); 
System.out.println("Binary Size: " + data.length);

// -------------------------------------------

// 3. 反序列化 (从 byte[] 转回对象)
try {
    VehicleStatus receivedStatus = VehicleStatus.parseFrom(data);
    
    // 访问数据
    System.out.println("Speed: " + receivedStatus.getSpeed());
    System.out.println("VIN: " + receivedStatus.getVinCode());
} catch (InvalidProtocolBufferException e) {
    e.printStackTrace();
}
```

### 5.2 C++ 侧使用

```cpp
#include "car_event.pb.h"
#include <iostream>
#include <fstream>

using namespace com::example::cockpit;

void serialization_example() {
    // 1. 构建对象
    VehicleStatus status;
    status.set_speed(120);
    status.set_vin_code("example12345678");
    status.set_is_moving(true);
    status.set_current_gear(VehicleStatus::GEAR_D);
    
    // 添加数组元素
    status.add_error_codes("E001");

    // 2. 序列化 (Serialize)
    std::string binary_output;
    if (status.SerializeToString(&binary_output)) {
        // binary_output 现在包含了序列化后的数据，可以发送到 Socket
    }
}

void deserialization_example(const std::string& data_in) {
    // 3. 反序列化 (Deserialize)
    VehicleStatus status;
    if (status.ParseFromString(data_in)) {
        std::cout << "Speed: " << status.speed() << std::endl;
        std::cout << "VIN: " << status.vin_code() << std::endl;
    }
}
```

-----

## 6. 最佳实践与注意事项

1.  **字段编号管理**：
      * **永远不要**修改已存在字段的 ID。如果必须修改，请新建一个字段，废弃旧字段。
      * 可以使用 `reserved` 关键字保留已删除的 ID，防止后续误用：
        ```protobuf
        reserved 3, 5 to 7;
        reserved "old_field_name";
        ```
2.  **默认值 (Proto3)**：
      * Proto3 不再支持手动设置 default 值。
      * 基础类型的默认值为：`int=0`, `bool=false`, `string=""`。
      * **注意**：如果一个字段的值等于默认值（例如 speed=0），序列化时该字段**不会**被写入二进制流（为了节省空间）。反序列化时如果读不到该字段，会直接赋予默认值。
3.  **兼容性设计**：
      * **新增字段**：旧代码读取新数据时，会忽略新字段（向后兼容）。
      * **删除字段**：新代码读取旧数据时，已删除字段会获得默认值（向前兼容）。