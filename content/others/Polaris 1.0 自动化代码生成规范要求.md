+++
date = '2025-12-24T17:17:50+08:00'
draft = true
title = 'Polaris 1.0 自动化代码生成规范要求'
+++

# Polaris 1.0 自动化代码生成规范要求

**Polaris Code Generation Specification**

| 版本   | 日期         | 作者           | 说明   |
| ---- | ---------- | ------------ | ---- |
| v1.0 | 2025-12-XX | Polaris Team | 初始版本 |

---

## 1. 目标与原则（Goals & Principles）

### 1.1 目标

自动化代码生成（Codegen）用于将 **全局事件注册表** 转换为：

* 强类型、可编译校验的 SDK 代码
* 跨语言一致（Java / C++）
* 可被 IDE 精准提示
* 在大规模事件数量下依然可维护
  
### 1.2 核心设计原则（强制）

| 原则                       | 说明                                |
| ------------------------ | --------------------------------- |
| **类型安全优先**               | 任何参数错误必须在**编译期或构造期**暴露            |
| **去中心化**                 | 禁止生成集中式 God Class（如 Reporter 聚合类） |
| **一事件一类型**               | 每个 Event 必须生成独立的 Context 类        |
| **构造即合法**                | 构造函数必须保证必填字段完整;可选字段提供setter方法                    |
| **生成代码可删可裁剪**            | 未使用事件允许被 R8 / Linker 移除           |
| **Core 稳定，Generated 易变** | Core SDK 不因新增事件而变化                |

---

## 2. 输入源规范（Source of Truth）

### 2.1 唯一输入源

自动化生成的**唯一可信输入源**为：

* `events.csv` / `events.xlsx`（注册表）
* 禁止从代码反向生成或手动补丁

### 2.2 关键字段映射关系

| 注册表字段          | 生成代码中的用途                 |
| -------------- | ------------------------ |
| EventID        | Context 构造函数中绑定          |
| EventName      | 类名 / 常量名                 |
| Desc_Schema    | 字段定义、构造函数参数              |
| Status         | 控制是否生成 / 是否标记 Deprecated |
| Logical_Module | 包名 / namespace 分组        |
| SDK_Type | 对应private final int SDK_TYPE    |
| SDK_LEVEL | 对应private final int SDK_LEVEL   |
---

## 3. 生成物总体结构规范

### 3.1 禁止生成的内容（❌ Hard Rules）

**Codegen 脚本必须遵守以下禁止项：**

❌ 不得生成：

* `PolarisReporter` / `EventManager` 等集中调度类
* `report(long id, Object...)` / `Map<String,Object>` 风格 API
* 反射、字符串拼字段名的逻辑
* 单文件包含多个 Event 的 Context 类

---

### 3.2 必须生成的内容（✅ Hard Rules）

| 生成物                  | 是否必须  | 说明                |
| -------------------- | ----- | ----------------- |
| `PolarisEvents`      | ✅     | EventID 常量定义      |
| `BasePolarisContext` | ❌（手写） | 位于 Core SDK       |
| `XxxContext`         | ✅     | 每个 Event 一个       |
| `@Deprecated` 注解     | ✅     | Status=Deprecated |

---

#### 核心规则逻辑
Java 包名: com.polaris.events.<scope>.<logical_module>
Scope: 取 EventName 的第一段（如 GVM -> gvm）。
Logical_Module: 取注册表 Logical_Module 列，转小写并去空格（如 AppManager -> appmanager）。
C++ 目录: include/polaris/events/<scope>/<logical_module>/
与 Java 包名逻辑保持完全一致，确保跨语言结构对称。

类名生成: EventName 转 PascalCase + Context
GVM_APP_ANR -> GvmAppAnrContext

防御性逻辑:
自动从 Desc_Schema 中剔除 tid, pid, proc, ver, logf，防止与基类 Common 字段冲突。
Java 常量使用 static {} 块初始化，防止编译器内联。


## 4. Context 类生成规范（核心）

### 4.1 类命名规则

```text
<EventName> + "Context"
```

示例：

| EventName          | Context 类名              |
| ------------------ | ----------------------- |
| SYS_WATCHDOG_RESET | SysWatchdogResetContext |
| APP_MAP_ANR        | AppMapAnrContext        |

---

### 4.2 包 / Namespace 规则（强制）

```text
com.polaris.events.<logical_module>.<scope>
```

示例：

```text
com.polaris.events.framework.sys
com.polaris.events.app.map
com.polaris.events.mcu.power
```

> 📌 Codegen 必须支持未来 **拆分为独立 AAR / jar / so**

---

### 4.3 字段与构造函数规则（强制）

#### 4.3.1 必填字段（Required）

* 必须：
  * 出现在构造函数参数列表
  * 在构造函数内赋值
* 禁止：
  * 提供 setter
  * 提供默认值
* Context类必须提供final int SDK_TYPE和final int SDK_LEVEL字段，变量值从events.csv中提取，并提供get方法
  
```java
public SysWatchdogResetContext(int pid, String reason) {
    super(PolarisEvents.SYS_WATCHDOG_RESET);
    this.pid = pid;
    this.reason = reason;
}
```

---

#### 4.3.2 可选字段（Optional）

* 不出现在构造函数中
* 必须通过链式 Setter 设置
* Setter 返回 `this`

```java
public AppMapAnrContext setActivity(String activity) {
    this.activity = activity;
    return this;
}
```

---

### 4.4 validate() 生成规范

Codegen 必须生成 `validate()` 方法，至少包含：

* Required 字段非空 / 合法性校验
* 枚举 / 范围校验（如有）

```java
@Override
public boolean validate() {
    return pid > 0 && reason != null;
}
```

---

### 4.5 report() 便捷方法

生成类 **必须包含**：

```java
public void report() {
    PolarisAgent.getInstance().report(this);
}
```

> 📌 该方法仅是语法糖，不得包含任何业务逻辑。

---

### 4.6 实现 toJson() 以及 toString() 方法

## 5. Deprecated 事件生成规则

当注册表中：

```text
Status = Deprecated
```

Codegen 必须：

1. 仍生成 Context 类（保证兼容旧代码）
2. 添加 `@Deprecated` 注解
3. Javadoc 标明替代 EventID（如有）

```java
/**
 * @deprecated Use SYS_WATCHDOG_RESET_V2 instead
 */
@Deprecated
public class SysWatchdogResetContext { ... }
```

---

## 6. PolarisEvents 常量类生成规范

### 6.1 职责边界

* **只允许**包含 `public static final long`
* 不允许方法
* 不允许逻辑

```java
public final class PolarisEvents {
    public static final long SYS_WATCHDOG_RESET = 6660000001L;
}
```

---

## 7. 跨语言一致性要求（Java / C++）

### 7.1 生成规则必须一致

| 维度       | Java             | C++              |
| -------- | ---------------- | ---------------- |
| 类/结构体    | class            | struct / class   |
| 构造函数     | 强制 Required      | 强制 Required      |
| Optional | Setter           | Setter           |
| validate | virtual override | virtual override |
| JSON     | JSONObject       | nlohmann::json   |

---

## 8. 生成代码质量要求

### 8.1 生成代码必须满足

* 可直接通过 `javac / clang` 编译
* 无 warning（-Wall）
* 不依赖反射
* 不依赖运行时 schema

---

## 9. 演进与兼容性要求

### 9.1 Schema 变更规则

| 变更类型                   | 是否允许          |
| ---------------------- | ------------- |
| 新增 Optional 字段         | ❌（需新 EventID） |
| 修改字段类型                 | ❌             |
| 修改 Required / Optional | ❌             |
| 修改 Owner / Desc        | ✅             |

> 📌 **Codegen 必须假设旧端代码永远存在**

---

## 10. 非目标（Non-Goals）

本规范 **不负责**：

* 事件分配流程
* 注册表评审机制
* 云端解析逻辑
* SDK 发送策略

---

## 11. 设计哲学

> **Codegen 的职责不是“省代码”，
> 而是把“错误”尽可能提前到：**
>
> * 编译期
> * 构造期
> * IDE 提示期

> **如果某个错误只能在运行时发现，
> 那就是 Codegen 的失败。**

---

## 12. 结语

这套自动化代码生成规范确保：

* 事件规模 ×1000，复杂度 ≈ ×1
* SDK 使用体验长期稳定
* 平台代码与业务事件彻底解耦

> **这是一个“为十年维护周期而设计”的 Codegen 规范。**

---

## 附录

1. java代码生成目录结构，可参考：
   ```txt
   generated/
    └── java/
        └── com/polaris/
            ├── constants/
            │   └── PolarisEvents.java
            │
            └── events/
                ├── sys/
                │   └── framework/
                │       ├── watchdog/
                │       │   └── SysWatchdogResetContext.java
                │       └── anr/
                │           └── SysServiceAnrContext.java
                │
                ├── app/
                │   └── map/
                │       └── anr/
                │           └── AppMapAnrContext.java
                │
                └── mcu/
                    └── power/
                        └── battery/
                            └── McuBatteryLowContext.java

   ```
2. C++代码生成目录结构，可参考：
   ```txt
   generated/
    └── cpp/
        ├── include/
        │   └── polaris/
        │       ├── constants/
        │       │   └── PolarisEvents.h
        │       │
        │       └── events/
        │           ├── sys/
        │           │   └── framework/
        │           │       └── watchdog/
        │           │           └── SysWatchdogResetContext.h
        │           │
        │           └── app/
        │               └── map/
        │                   └── anr/
        │                       └── AppMapAnrContext.h
        │
        └── src/
            └── events/
                └── ...

   ```

2. 参考代码实现：

```python
import csv
import os
import sys
from dataclasses import dataclass
from typing import List, Set
from jinja2 import Environment, BaseLoader

# ==========================================
# 1. 全局配置与规范定义
# ==========================================

OUTPUT_DIR = "generated"

# 类型映射表 (Spec 7.1)
TYPE_MAPPING = {
    "int":    ("int", "int32_t"),
    "long":   ("long", "int64_t"),
    "string": ("String", "std::string"),
    "float":  ("float", "float"),
    "bool":   ("boolean", "bool"),
}

# 规范 3.2: 后缀白名单 (包含最新的 _STAT)
VALID_SUFFIXES = {
    # 致命异常
    "_CRASH", "_ANR", "_RESET", "_OOM", "_KILLED", "_BLANK",
    # 性能体验
    "_SLOW", "_BLOCK", "_JANK", "_TIMEOUT", "_BUSY",
    # 资源泄漏
    "_LEAK", "_HIGH", "_LOW",
    # 链路管控
    "_LOST", "_REJECT", "_FAIL",
    # 统计与趋势 (New)
    "_STAT"
}

# 系统保留字段 (Common Fields)，严禁出现在 Desc_Schema 生成的代码中
RESERVED_FIELDS = {"tid", "pid", "proc", "ver", "logf"}

# ==========================================
# 2. 数据模型
# ==========================================

@dataclass
class Field:
    name: str
    schema_type: str
    is_optional: bool

    @property
    def java_type(self):
        return TYPE_MAPPING[self.schema_type][0]

    @property
    def cpp_type(self):
        return TYPE_MAPPING[self.schema_type][1]

    @property
    def name_capitalized(self):
        return self.name[0].upper() + self.name[1:]


@dataclass
class EventContext:
    event_id: str
    event_name: str
    logical_module: str
    owner: str
    sdk_type: str
    sdk_level: str
    status: str
    fields: List[Field]

    @property
    def class_name(self):
        # Rule: PascalCase + Context
        # GVM_APP_ANR -> GvmAppAnrContext
        parts = self.event_name.split('_')
        return "".join(p.capitalize() for p in parts) + "Context"

    @property
    def scope(self):
        # Rule: Extract first part of EventName as Scope
        # GVM_APP_ANR -> gvm
        parts = self.event_name.split('_')
        if not parts:
            raise ValueError(f"Invalid EventName format: {self.event_name}")
        return parts[0].lower()

    @property
    def module_clean(self):
        # Rule: Logical_Module to lowercase, remove spaces
        # "AppManager" -> "appmanager"
        return self.logical_module.lower().replace(" ", "")

    @property
    def package_name(self):
        # Java Package: com.polaris.events.<scope>.<logical_module>
        return f"com.polaris.events.{self.scope}.{self.module_clean}"

    @property
    def cpp_namespace(self):
        # C++ Namespace: polaris::events::<scope>::<logical_module>
        return f"polaris::events::{self.scope}::{self.module_clean}"

    @property
    def is_deprecated(self):
        return self.status.lower() == "deprecated"

    @property
    def required_fields(self):
        return [f for f in self.fields if not f.is_optional]

    @property
    def optional_fields(self):
        return [f for f in self.fields if f.is_optional]


# ==========================================
# 3. 模板定义 (Jinja2)
# ==========================================

# Java Template
# 更新点：不生成 Common 字段；支持 setLogRef 等
JAVA_TEMPLATE = """package {{ event.package_name }};

import com.polaris.constants.PolarisEvents;
import com.polaris.core.BasePolarisContext;
import com.polaris.core.PolarisAgent;
import org.json.JSONObject;

/**
 * Auto-generated by polaris-codegen.
 * Event: {{ event.event_name }} ({{ event.event_id }})
 * Logic Module: {{ event.logical_module }}
 * Owner: {{ event.owner }}
 */
{% if event.is_deprecated %}@Deprecated{% endif %}
public class {{ event.class_name }} extends BasePolarisContext {

    // SDK Metadata
    private final int sdkType = {{ event.sdk_type }};
    private final int sdkLevel = {{ event.sdk_level }};

    // Business Fields (Desc_Schema)
    {% for field in event.fields %}
    private {{ field.java_type }} {{ field.name }};
    {% endfor %}

    // Constructor (Required Fields Only)
    public {{ event.class_name }}({% for field in event.required_fields %}{{ field.java_type }} {{ field.name }}{% if not loop.last %}, {% endif %}{% endfor %}) {
        super(PolarisEvents.{{ event.event_name }});
        {% for field in event.required_fields %}
        this.{{ field.name }} = {{ field.name }};
        {% endfor %}
    }

    // Setters (Optional Fields)
    {% for field in event.optional_fields %}
    public {{ event.class_name }} set{{ field.name_capitalized }}({{ field.java_type }} {{ field.name }}) {
        this.{{ field.name }} = {{ field.name }};
        return this;
    }
    {% endfor %}

    @Override
    public boolean validate() {
        {% for field in event.required_fields %}
        {% if field.schema_type == 'string' %}
        if (this.{{ field.name }} == null) return false;
        {% endif %}
        {% endfor %}
        return true;
    }

    @Override
    public JSONObject toJson() {
        JSONObject json = new JSONObject();
        // Desc_Schema Fields
        {% for field in event.fields %}
        json.put("{{ field.name }}", this.{{ field.name }});
        {% endfor %}
        return json;
    }

    // Reporting
    public void report() {
        PolarisAgent.getInstance().report(this);
    }
}
"""

# C++ Template
CPP_TEMPLATE = """#pragma once

#include <string>
#include <nlohmann/json.hpp>
#include "polaris/constants/PolarisEvents.h"
#include "polaris/core/BasePolarisContext.h"

namespace {{ event.cpp_namespace }} {

/**
 * Event: {{ event.event_name }} ({{ event.event_id }})
 */
{% if event.is_deprecated %}[[deprecated]]{% endif %}
class {{ event.class_name }} : public polaris::core::BasePolarisContext {
public:
    const int32_t sdk_type = {{ event.sdk_type }};
    const int32_t sdk_level = {{ event.sdk_level }};

    {% for field in event.fields %}
    {{ field.cpp_type }} {{ field.name }};
    {% endfor %}

    {{ event.class_name }}({% for field in event.required_fields %}{{ field.cpp_type }} {{ field.name }}_in{% if not loop.last %}, {% endif %}{% endfor %}) 
        : BasePolarisContext(polaris::constants::{{ event.event_name }}) {
        {% for field in event.required_fields %}
        this->{{ field.name }} = {{ field.name }}_in;
        {% endfor %}
    }

    {% for field in event.optional_fields %}
    {{ event.class_name }}& set{{ field.name_capitalized }}({{ field.cpp_type }} {{ field.name }}_in) {
        this->{{ field.name }} = {{ field.name }}_in;
        return *this;
    }
    {% endfor %}

    nlohmann::json toJson() const override {
        nlohmann::json j;
        {% for field in event.fields %}
        j["{{ field.name }}"] = this->{{ field.name }};
        {% endfor %}
        return j;
    }
};

} // namespace
"""

# Constants Java Template (防止内联)
CONSTANTS_JAVA_TEMPLATE = """package com.polaris.constants;

/**
 * Auto-generated Event IDs.
 * Source of Truth: events.csv
 * NOTE: IDs are initialized in a static block to prevent Java compiler inlining.
 */
public final class PolarisEvents {
    // Definitions
    {% for event in events %}
    public static final long {{ event.event_name }};
    {% endfor %}

    // Initialization
    static {
        {% for event in events %}
        {{ event.event_name }} = {{ event.event_id }}L;
        {% endfor %}
    }
}
"""

# Constants C++ Template
CONSTANTS_CPP_TEMPLATE = """#pragma once
#include <cstdint>

namespace polaris::constants {
    {% for event in events %}
    constexpr int64_t {{ event.event_name }} = {{ event.event_id }};
    {% endfor %}
}
"""

# ==========================================
# 4. 逻辑处理函数
# ==========================================

def parse_schema(schema_str: str, event_name: str) -> List[Field]:
    fields = []
    if not schema_str or schema_str.upper() == 'NONE':
        return fields

    # 支持分号或逗号分隔 "pid:int; reason:string"
    delimiter = ';' if ';' in schema_str else ','
    
    for item in [x.strip() for x in schema_str.split(delimiter)]:
        if ':' not in item: continue

        name, raw_type = item.split(':')
        name = name.strip()
        
        # [Defensive] 自动过滤系统保留字段
        if name in RESERVED_FIELDS:
            print(f"⚠️ Warning: Ignored reserved field '{name}' in {event_name}. It is handled by BaseContext.")
            continue
            
        is_optional = raw_type.endswith('?')
        schema_type = raw_type.rstrip('?')

        if schema_type not in TYPE_MAPPING:
            raise ValueError(f"❌ Type Error in {event_name}: Unsupported type '{schema_type}'")

        fields.append(Field(name, schema_type, is_optional))

    return fields

def validate_event_name_suffix(name: str):
    valid = False
    for suffix in VALID_SUFFIXES:
        if name.endswith(suffix):
            valid = True
            break
    if not valid:
        raise ValueError(f"❌ Naming Violation: '{name}' suffix not in whitelist.")

# ==========================================
# 5. 主生成流程
# ==========================================

def generate_code():
    print("🚀 Starting Polaris Codegen...")
    
    # 目录检查
    if not os.path.exists("generated"):
        os.makedirs("generated")

    events: List[EventContext] = []
    
    try:
        with open("events.csv", mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row.get("EventID"): continue
                
                eid = row["EventID"]
                ename = row["EventName"]
                
                # 校验
                validate_event_name_suffix(ename)
                
                # 解析 Schema (自动去除 Common 字段)
                fields = parse_schema(row["Desc_Schema"], ename)

                event = EventContext(
                    event_id=eid,
                    event_name=ename,
                    logical_module=row["Logical_Module"], # e.g. "AppManager"
                    owner=row["Owner"],
                    sdk_type=row["SDK_Type"],
                    sdk_level=row["SDK_Level"],
                    status=row["Status"],
                    fields=fields
                )
                events.append(event)

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

    env = Environment(loader=BaseLoader())

    # 生成 Java/C++ Context 类
    for event in events:
        # Java Path: generated/java/com/polaris/events/<scope>/<module>/
        java_pkg_path = event.package_name.replace('.', '/')
        java_full_path = os.path.join(OUTPUT_DIR, "java", java_pkg_path)
        os.makedirs(java_full_path, exist_ok=True)
        
        with open(os.path.join(java_full_path, f"{event.class_name}.java"), "w") as f:
            f.write(env.from_string(JAVA_TEMPLATE).render(event=event))

        # C++ Path: generated/cpp/include/polaris/events/<scope>/<module>/
        # 对应 namespace: polaris::events::<scope>::<module>
        cpp_ns_path = os.path.join("polaris", "events", event.scope, event.module_clean)
        cpp_full_path = os.path.join(OUTPUT_DIR, "cpp", "include", cpp_ns_path)
        os.makedirs(cpp_full_path, exist_ok=True)

        with open(os.path.join(cpp_full_path, f"{event.class_name}.h"), "w") as f:
            f.write(env.from_string(CPP_TEMPLATE).render(event=event))

    # 生成 Constants
    # Java
    const_java_path = os.path.join(OUTPUT_DIR, "java", "com", "polaris", "constants")
    os.makedirs(const_java_path, exist_ok=True)
    with open(os.path.join(const_java_path, "PolarisEvents.java"), "w") as f:
        f.write(env.from_string(CONSTANTS_JAVA_TEMPLATE).render(events=events))
        
    # C++
    const_cpp_path = os.path.join(OUTPUT_DIR, "cpp", "include", "polaris", "constants")
    os.makedirs(const_cpp_path, exist_ok=True)
    with open(os.path.join(const_cpp_path, "PolarisEvents.h"), "w") as f:
        f.write(env.from_string(CONSTANTS_CPP_TEMPLATE).render(events=events))

    print(f"✅ Generated {len(events)} events.")
    print(f"📂 Java Root: {os.path.join(OUTPUT_DIR, 'java')}")
    print(f"📂 C++ Root:  {os.path.join(OUTPUT_DIR, 'cpp')}")

if __name__ == "__main__":
    generate_code()
```