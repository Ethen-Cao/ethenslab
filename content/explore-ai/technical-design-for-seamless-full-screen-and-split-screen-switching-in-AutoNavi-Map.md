+++
date = '2025-08-04T09:49:58+08:00'
draft = false
title = 'Technical Design for Seamless Full Screen and Split Screen Switching in AutoNavi Map'
+++

## 需求背景

1. 核心功能
基于 Android 平台 及 高德AutoSDK，开发一个车载地图应用。该应用需具备两种核心显示形态：

* 全屏模式: 地图占据整个屏幕，提供沉浸式导航体验。
* 分屏模式: 屏幕左侧约1/3区域显示车辆信息面板（如车模、转向灯状态等），右侧约2/3区域显示地图信息。

2. 交互要求

* 应用界面下方存在一个常驻的Dock栏，栏上有一个“地图”按钮。
* 用户通过反复点击此按钮，可以在“全屏模式”与“分屏模式”之间循环切换。

3. 质量要求
* “丝滑”过渡: 两种模式之间的切换过程必须是流畅的动画，不能有任何视觉上的中断。
* “三无”标准: 切换动画过程中，严禁出现任何黑屏、闪烁或卡顿掉帧现象，以确保高端、流畅的用户体验。

## 技术挑战与选型

1. 主要挑战
在Android平台上，对一个正在进行实时、复杂内容渲染的视图（如地图）进行尺寸和位置的变更，是一项极具挑战性的任务。传统的视图动画或直接改变窗口尺寸的方案，往往会触发底层的Window重绘或Surface重建，这个过程耗时较长，极易导致以下问题：
* 闪烁/黑屏: 在旧的Surface被销毁、新的Surface尚未完全渲染内容的短暂间隙，屏幕会出现背景色或黑色，造成视觉闪烁。
* 卡顿: 如果布局计算和视图重绘的耗时超过了Android系统的一帧渲染时间（约16.6ms），就会导致掉帧，动画看起来就会卡顿、不连贯。

2. 核心方案选型
为了克服上述挑战，我们选择采用Android官方推荐的、专为复杂UI动画设计的现代技术栈：MotionLayout + TextureView。
* MotionLayout：作为ConstraintLayout的子类，它专为动画而生。它允许我们以声明式的方式在XML中定义多个布局状态，并由系统在底层高效地计算和执行状态之间的过渡动画，性能极高且能轻松处理多视图联动。
* TextureView：高德SDK默认可能使用SurfaceView渲染，它拥有独立的绘图表面，会“打穿”应用窗口，与Android的常规视图动画体系不兼容，是闪烁的主要根源。通过AMapOptions强制SDK使用TextureView，地图内容将被渲染到一个标准的图形纹理上，可以像普通View一样无缝参与到MotionLayout的动画体系中。

## 详细实现方案

### 强制TextureView并初始化SDK

MainActivity.kt
```java
class MainActivity : AppCompatActivity() {

    private lateinit var motionLayout: MotionLayout
    private lateinit var mapView: TextureMapView
    private lateinit var mapContainer: CardView
    private lateinit var carModelPanel: LinearLayout
    private lateinit var toggleButton: FloatingActionButton
    private var isFullScreen = true

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // 设置包含MotionLayout的主布局文件
        setContentView(R.layout.activity_main_split)
        supportActionBar?.hide()

        MapsInitializer.updatePrivacyAgree(this,true);
        MapsInitializer.updatePrivacyShow(this,true,true);
        // 初始化视图
        motionLayout = findViewById(R.id.motion_layout_main)
        mapContainer = findViewById(R.id.map_container_card)
        carModelPanel = findViewById(R.id.car_model_panel)
        toggleButton = findViewById(R.id.fab_toggle_map)

        // 1. Create the options object
        val aMapOptions = AMapOptions()
        
        // 2. CRITICAL: Force the use of TextureView
        //aMapOptions.useTextureView(true)
        
        // 3. Pass the options into the MapView constructor
        mapView = TextureMapView(this)
        
        // 4. Add the MapView to its container
        val mapContainer: CardView = findViewById(R.id.map_container_card)
        mapContainer.addView(mapView)
        
        // 5. Forward the lifecycle event
        mapView.onCreate(savedInstanceState)


        // --- 控制动画的核心逻辑 ---
        toggleButton.setOnClickListener {
            if (isFullScreen) {
                // 如果当前是全屏，则过渡到分屏状态
                motionLayout.transitionToEnd()
            } else {
                // 如果当前是分屏，则过渡回全屏状态
                motionLayout.transitionToStart()
            }
            isFullScreen = !isFullScreen
        }
    }

    // --- 严格管理高德SDK的生命周期 ---
    // 这是确保地图正常显示、避免内存泄漏的必要步骤

    override fun onResume() {
        super.onResume()
        mapView.onResume()
    }

    override fun onPause() {
        super.onPause()
        mapView.onPause()
    }

    override fun onDestroy() {
        super.onDestroy()
        mapView.onDestroy()
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        mapView.onSaveInstanceState(outState)
    }
}
```

### 布局实现 (MotionLayout)
我们使用MotionLayout作为根布局，并在其中定义两个核心功能区：车模面板和地图容器。

app/src/main/res/layout/activity_main_split.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<androidx.constraintlayout.motion.widget.MotionLayout
    xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto"
    xmlns:tools="http://schemas.android.com/tools"
    android:id="@+id/motion_layout_main"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:background="#111827"
    app:layoutDescription="@xml/scene_split"
    tools:context=".MainActivity">

    <!-- 左侧车模信息面板 -->
    <LinearLayout
        android:id="@+id/car_model_panel"
        android:layout_width="0dp"
        android:layout_height="match_parent"
        android:background="#2D3748"
        android:gravity="center"
        android:orientation="vertical">
        <!-- 在这里放置您的车模View、转向灯信息等 -->
        <TextView
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:text="车模信息"
            android:textColor="@android:color/white"
            android:textSize="24sp" />
    </LinearLayout>

    <!--
    地图容器：我们使用CardView来包裹MapView，
    这样可以方便地控制背景和阴影（如果需要）。
    动画将作用于这个CardView上。
    -->
    <androidx.cardview.widget.CardView
        android:id="@+id/map_container_card"
        android:layout_width="0dp"
        android:layout_height="match_parent"
        app:cardBackgroundColor="@android:color/transparent"
        app:cardElevation="0dp" />

    <!--
    模拟的Dock栏按钮：使用悬浮按钮(FloatingActionButton)
    来触发全屏/分屏的切换。
    -->
    <com.google.android.material.floatingactionbutton.FloatingActionButton
        android:id="@+id/fab_toggle_map"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:layout_margin="24dp"
        app:srcCompat="@android:drawable/ic_menu_slideshow"
        app:layout_constraintBottom_toBottomOf="parent"
        app:layout_constraintEnd_toEndOf="parent" />

</androidx.constraintlayout.motion.widget.MotionLayout>
```

### 动画定义 (MotionScene)

res/xml/scene_split.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<MotionScene xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:app="http://schemas.android.com/apk/res-auto">

    <!-- 定义一个从全屏(start)到分屏(end)的过渡 -->
    <Transition
        app:constraintSetEnd="@+id/split_screen_state"
        app:constraintSetStart="@+id/fullscreen_state"
        app:duration="600"
        app:motionInterpolator="cubic(0.65,0,0.35,1)"> <!-- 使用缓动曲线，效果更自然 -->
    </Transition>

    <!-- 状态1: 全屏 (start) -->
    <ConstraintSet android:id="@+id/fullscreen_state">
        <!-- 地图容器填满整个屏幕 -->
        <Constraint
            android:id="@+id/map_container_card"
            android:layout_width="0dp"
            android:layout_height="match_parent"
            app:layout_constraintStart_toStartOf="parent"
            app:layout_constraintEnd_toEndOf="parent" />

        <!-- 车模面板在屏幕左侧外部，为动画做准备 -->
        <Constraint
            android:id="@+id/car_model_panel"
            android:layout_width="0dp"
            app:layout_constraintWidth_percent="0.33"
            android:layout_height="match_parent"
            app:layout_constraintEnd_toStartOf="parent" />
    </ConstraintSet>

    <!-- 状态2: 分屏 (end) -->
    <ConstraintSet android:id="@+id/split_screen_state">
        <!-- 车模面板占据左侧1/3 -->
        <Constraint
            android:id="@+id/car_model_panel"
            android:layout_width="0dp"
            app:layout_constraintWidth_percent="0.33"
            android:layout_height="match_parent"
            app:layout_constraintStart_toStartOf="parent" />

        <!-- 地图容器占据右侧2/3 -->
        <Constraint
            android:id="@+id/map_container_card"
            android:layout_width="0dp"
            android:layout_height="match_parent"
            app:layout_constraintStart_toEndOf="@id/car_model_panel"
            app:layout_constraintEnd_toEndOf="parent" />

        <!-- 让切换按钮保持在右下角，不受地图容器尺寸变化影响 -->
        <Constraint
            android:id="@+id/fab_toggle_map"
            android:layout_width="wrap_content"
            android:layout_height="wrap_content"
            android:layout_margin="24dp"
            app:layout_constraintBottom_toBottomOf="parent"
            app:layout_constraintEnd_toEndOf="parent" />
    </ConstraintSet>

</MotionScene>

```

### 触发动画
业务代码变得极其简洁，只需在适当的时机调用MotionLayout的API即可。

MainActivity.kt
```java
// ...
// 在按钮的onClick事件中
toggleButton.setOnClickListener {
    if (isFullScreen) {
        motionLayout.transitionToEnd() // 过渡到分屏状态
    } else {
        motionLayout.transitionToStart() // 过渡回全屏状态
    }
    isFullScreen = !isFullScreen
}
// ...
```

## 原理剖析
动画之所以能做到“丝滑”且“无变形”，其底层遵循一个高效的协作流程：

![动画流程](/ethenslab/static/images/AMapView-animation.png)

从上图可见，用户看到的平滑缩放，并非是对一幅大图的挤压，而是一系列尺寸连续变化、但内容比例始终正常的画面，以极高帧率连续播放的结果。这个流程完全在一帧（~16.6ms）内完成，从而实现了无缝过渡。