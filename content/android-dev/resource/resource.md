+++
date = '2025-08-08T11:36:11+08:00'
draft = false
title = 'Resource'
+++

## Theme

Android的**Theme（主题）**，简单来说，就是一组预定义的视觉样式和属性集合，应用于整个应用或界面，决定界面元素的颜色、字体、控件样式、间距、背景等外观表现。

---

### 详细解释

* **作用**：统一管理应用界面风格，保持整体视觉一致性，避免在每个控件上单独设置样式。
* **内容**：包含颜色（primary color、accent color等）、文字样式、按钮样式、控件默认背景、动画、间距、图标等多种属性。
* **继承**：Theme是基于`style`构建的，且支持继承，常见有系统默认主题（如`Theme.Holo`、`Theme.MaterialComponents`），开发者可继承这些主题自定义。
* **应用范围**：

  * **全局**：在`AndroidManifest.xml`中通过`application`标签的`android:theme`属性设置，影响整个App。
  * **局部**：可在`Activity`或`View`中单独设置，覆盖全局主题。

---

### 举例

```xml
<!-- 应用主题 -->
<style name="AppTheme" parent="Theme.MaterialComponents.DayNight.NoActionBar">
    <item name="colorPrimary">@color/my_primary_color</item>
    <item name="colorAccent">@color/my_accent_color</item>
    <!-- 更多自定义属性 -->
</style>
```

在`AndroidManifest.xml`：

```xml
<application
    android:theme="@style/AppTheme"
    ...>
```

---

### 主题与样式的区别

* **样式（Style）**：作用于单个View控件的外观定义（如按钮颜色、字体大小）。
* **主题（Theme）**：是作用于整个界面或应用的样式集合，包含大量样式属性，能控制全局控件默认行为和外观。

---

### 主题的演进

* **Theme.Holo**：Android 3.x 引入的较早现代主题。
* **Theme.AppCompat**：支持旧版本Android的兼容库主题，广泛使用。
* **Theme.MaterialComponents**：实现Material Design规范，适合Android 5.0及以上。
* **Theme.Material3**：最新Material You设计，支持动态色彩等新特性。

---

Android主题演进和结构的图参考如下：

![Android主题演进](/ethenslab/images/theme.png)

---

### 平台主题

**平台主题（Platform Theme）**，指的是 Android 操作系统自身提供的、内置在系统框架中的主题样式集合。它们是 Android 系统从一开始就带有的基础视觉风格，定义了系统默认的界面外观和控件样式。

---

#### 详细说明

* **由谁提供**：由 Android 系统平台（Framework）自带，随着系统版本升级而演进和扩展。
* **作用**：为所有应用和系统界面提供默认的视觉风格基准。
* **特点**：

  * 包含了一系列基础样式属性，例如颜色、字体、控件样式、背景等。
  * 应用默认继承平台主题（如果没有显式指定主题），保证了不同应用界面风格的一致性。
  * 是所有兼容库主题（如 AppCompat）和第三方主题的基底。

---

#### 常见的平台主题

| 主题名称                    | 适用API版本                    | 特点                          |
| ----------------------- | -------------------------- | --------------------------- |
| **Theme**               | API 1+                     | 最基础的系统主题                    |
| **Theme.Holo**          | API 11（Android 3.0）到API 20 | 现代化蓝色调主题，首次引入较统一的视觉风格       |
| **Theme.Material**      | API 21（Android 5.0）及以后     | 实现 Google Material Design规范 |
| **Theme.DeviceDefault** | API 14+                    | 根据设备定制的默认主题                 |

---

#### 为什么要用平台主题？

* **兼容性**：系统提供的主题保证应用在不同Android版本上的基本一致性和兼容性。
* **性能**：系统主题经过优化，能保证界面流畅。
* **扩展性**：开发者可以基于平台主题进一步自定义自己的主题。

---

#### 平台主题与AppCompat主题的关系

* AppCompat是 Google 支持库提供的兼容方案，允许在旧版本Android（比如API 14以下）也能使用现代风格的控件和主题。
* AppCompat主题是基于平台主题（Holo 或 Material）做了二次封装和增强，实现更广泛的兼容。

---

平台主题演进：

![Android platform theme](ethenslab/images/platform-theme.png)

---

## Android uiMode 变化与主题加载机制

![Android uiMode 变化与主题加载机制](ethenslab/images/theme.png)

## Android 主题加载以及属性查找流程

![Android uiMode 变化与主题加载机制](/ethenslab/images/android-theme-resolve.png)

