+++
date = '2025-08-27T17:17:50+08:00'
draft = false
title = 'UML中package和component对比'
+++

## 一、概念本质对比

| 维度              | package                | component           |
| --------------- | ---------------------- | ------------------- |
| UML 原义          | 逻辑分组 / 命名空间            | 可独立替换的模块 / 软件部件     |
| 主要用途            | 分组元素、子系统容器             | 表示系统的可部署模块或功能单元     |
| 内部可以包含          | 类、其他 package、component | 组件接口、类、子模块          |
| 可独立部署           | ❌（只是命名空间）              | ✅（可以单独部署 / 替换）      |
| 是否表示具体功能        | ❌（仅概念分组）               | ✅（提供服务或功能）          |
| 可用在 Layer 图     | 不推荐                    | 不推荐（除非强调模块）         |
| 可用在 Subsystem 图 | ✅                      | ✅（子模块）              |
| 可显示接口 / 关系      | 部分可以                   | 可以显示接口、依赖关系、提供/使用接口 |

---

## 二、工程实践对比

### 1️⃣ package

* **语义**：一个“逻辑容器”，表示“这一块归为同一类别 / 子系统”。
* **场景**：

  * Android Framework
  * Linux Kernel
  * System Server
* **特点**：

  * 里面可以再有组件或类
  * 主要用于“整体边界”
* **建模目的**：

  * 显示子系统边界
  * 不关心模块内部实现细节
* **PlantUML 使用**：

  ```plantuml
  package "Android Framework" {
      component ActivityManager
      component WindowManager
  }
  ```

---

### 2️⃣ component

* **语义**：软件的可独立模块，提供接口，可替换。
* **场景**：

  * Android Service（AudioService、SurfaceFlinger）
  * HAL 模块（Camera HAL、Audio HAL）
  * 微服务 / 独立可部署模块
* **特点**：

  * 可以显示提供 / 使用接口
  * 可独立替换或部署
  * 可以嵌套在 package 内
* **PlantUML 使用**：

  ```plantuml
  package "Native HAL" {
      component "Audio HAL"
      component "Camera HAL"
  }
  ```

---

## 三、总结一句话

> **package = 逻辑分组 / 子系统容器，component = 功能模块 / 可部署单元。**
> 在 Layer 图里一般不使用 package/component（都用 rectangle）；在 Subsystem 图里，package 用于表示子系统，component 用于表示子系统内部模块或服务。

---

## 四、推荐使用规则（工程实践）

| 视图类型                   | package       | component       |
| ---------------------- | ------------- | --------------- |
| 架构分层图（Layer View）      | ❌             | ❌（都用 rectangle） |
| 子系统设计图（Subsystem View） | ✅（表示子系统）      | ✅（表示模块/服务）      |
| 展开子系统内部                | 可嵌套其他 package | 用于功能模块          |
| 显示接口 / 依赖关系            | 不显示           | 可以显示接口 / 提供使用   |

---


