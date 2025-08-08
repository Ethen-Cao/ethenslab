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

