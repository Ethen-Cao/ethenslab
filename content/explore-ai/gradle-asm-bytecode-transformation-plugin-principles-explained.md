+++
date = '2025-08-03T17:17:50+08:00'
draft = true
title = 'Gradle Asm Bytecode Transformation Plugin Principles Explained'
+++

# Gradle ASM 字节码转换插件原理解析

## 引言：问题与解决方案
问题：在软件开发中，我们经常会使用一些在高版本 API 中才出现的新方法。例如，java.io.InputStream.readAllBytes() 方法是在 Java 9 中引入的，对应到 Android 平台则是在 API Level 33 (Android 13) 中才可用。当一个应用设置的 minSdk 低于 33 时，如果在代码中直接调用此方法，应用在低版本 Android 设备上运行时会因为找不到该方法而抛出 NoSuchMethodError 异常，导致程序崩溃。

解决方案：为了解决这个问题，我们需要一种机制，在应用打包之前，自动将这些新 API 的调用替换为我们自己编写的、能在所有版本上运行的兼容性代码。这个过程通常被称为“API 脱糖 (API Desugaring)”。虽然 Android 的构建工具链内置了部分脱糖功能，但它并不涵盖所有情况。

我们采用的解决方案是创建一个自定义的 Gradle 插件，它利用 Android Gradle 插件 (AGP) 提供的转换 API 和 ASM 字节码操作框架，在编译期直接修改生成的 .class 文件，从根本上解决 API 的兼容性问题。

## 核心概念
要理解这个插件，首先需要了解几个核心概念：

* Java 字节码 (.class 文件)：Java 编译器 (javac) 并不直接生成机器码，而是将 .java 源代码编译成一种平台无关的中间指令集，即 Java 字节码，并保存在 .class 文件中。

* Android 运行时 (ART)：Android 设备不直接运行 Java 字节码，而是运行经过优化的 DEX (Dalvik Executable) 格式的字节码。在构建过程中，有一个名为 D8 的工具会将所有的 .class 文件和依赖库转换并合并成一个或多个 classes.dex 文件。

* ASM 框架：这是一个非常强大且高性能的 Java 字节码操作和分析框架。它允许我们以编程方式读取 .class 文件的内容，分析其结构（如类、方法、指令），甚至直接修改这些内容，然后再写回文件。这是我们实现字节码替换的核心工具。

## 插件架构与工作流程

我们自定义的插件，精确地插入到 javac 编译之后、D8 DEX 化之前的构建环节中。

![字节码转换插件工作流程](/ethenslab/images/java-bytes-transform.png)

### 详细步骤
1. 插件加载与注册 (DesugarTransformPlugin)
    * 当 Gradle 构建开始时，它会加载我们在 build-logic 中定义的插件。
    * 插件的 apply(Project) 方法是入口。在这里，我们通过 project.extensions.getByType(AndroidComponentsExtension::class.java) 获取到 AGP 的组件扩展。
    * 我们调用 androidComponents.onVariants 来遍历项目的所有构建变体（如 debug, release）。
    * 最关键的一步是调用 variant.instrumentation.transformClassesWith()。这个方法告诉 AGP：“对于这个变体的所有类，请使用我指定的工厂类 (ReadAllBytesClassVisitorFactory) 来创建一个转换器去处理它们。”

2. 转换器工厂 (ReadAllBytesClassVisitorFactory)

    * 这是一个实现了 AsmClassVisitorFactory 接口的工厂类。
    * AGP 在处理每一个 .class 文件时，都会调用这个工厂的 createClassVisitor() 方法。
    * 这个方法的作用是实例化一个我们自定义的 ClassVisitor (ReadAllBytesClassVisitor)，并将原始的 .class 文件内容作为输入流传递给它。
    * 我们还在这里为 ClassVisitor 的构造函数传入了 Opcodes.ASM9，这是一个版本号，用于告诉 ASM 我们期望使用哪个版本的 API 来进行操作，确保了兼容性。

3. 类访问器 (ReadAllBytesClassVisitor)
    * 这个类继承自 ASM 的 ClassVisitor。它的工作就像一个巡视员，负责“访问”一个类的各个组成部分，比如类名、父类、接口、字段以及最重要的方法。
    * 当它“访问”到类中的每一个方法时，它会重写 visitMethod() 方法。
    * 在 visitMethod() 中，它会创建一个专门负责处理方法内部指令的 MethodVisitor (ReadAllBytesMethodVisitor)。

4. 方法访问器 (ReadAllBytesMethodVisitor)
    * 这是真正执行替换操作的地方。我们使用了 AdviceAdapter，它是 MethodVisitor 的一个方便的子类。
    * AdviceAdapter 会遍历一个方法中的每一条字节码指令。
    * 我们重写了 visitMethodInsn() 方法。ASM 在遍历指令时，每当遇到一条方法调用指令（如 INVOKEVIRTUAL, INVOKESTATIC 等），就会自动回调这个方法。

## 核心逻辑：查找与替换
在 visitMethodInsn() 方法中，我们执行了精确的“查找-替换”逻辑：

### 查找
我们检查传入的指令参数，判断它是否是我们想要替换的目标：

* opcode == Opcodes.INVOKEVIRTUAL: 检查这是否是一个普通的实例方法调用（非静态、非私有等）。

* owner == "java/io/InputStream": 检查这个方法所属的类是否是 java.io.InputStream。

* name == "readAllBytes": 检查方法名是否是 readAllBytes。

* descriptor == "()[B": 检查方法的签名（描述符）。() 表示没有参数，[B 表示返回值是 byte 数组 (byte[])。

## 替换
如果以上所有条件都满足，我们就找到了目标。此时，我们不再调用 super.visitMethodInsn() 并传入原始的参数，而是用新的参数去调用它，从而实现指令的重写：

* opcode = Opcodes.INVOKESTATIC: 将指令从“实例方法调用”改为“静态方法调用”。
* owner = "com/example/desugartransform/CompatInputStream": 将方法所属的类改为我们自己编写的兼容性工具类。
* descriptor = "(Ljava/io/InputStream;)[B": 这是最关键的改变。我们将方法签名从“无参”改为“接收一个 InputStream 对象作为参数”。

### 为什么这样可行？—— 操作数栈的奥秘
在 JVM 字节码执行模型中，方法调用依赖于一个叫做“操作数栈”的结构。
* 在执行原始的 input.readAllBytes()（即 INVOKEVIRTUAL）之前，JVM 会先把 input 这个 InputStream 实例的引用压入操作数栈的栈顶
* 当我们的插件将指令替换为 INVOKESTATIC 时，栈顶的那个 InputStream 实例引用依然存在。
* 我们新的静态方法 CompatInputStream.readAllBytes(InputStream) 正好需要一个 InputStream 类型的参数。INVOKESTATIC 指令会自动从操作数栈中弹出这个引用，并将其作为参数传递给我们的静态方法。

因此，整个替换过程对于操作数栈的状态来说是完全平衡和兼容的，确保了修改后的字节码依然合法有效。

## 结论
通过 Gradle 插件机制，我们成功地将自己编写的、基于 ASM 的字节码转换逻辑注入到了 Android 的标准构建流程中。这个插件能够自动、精确地找到所有对不兼容 API (InputStream.readAllBytes()) 的调用，并将其无缝地替换为我们提供的、能在所有 Android 版本上运行的兼容实现 (CompatInputStream.readAllBytes())。

这不仅从根本上解决了应用的运行时崩溃问题，而且对开发者是完全透明的——开发者可以继续编写现代化的代码，而兼容性问题则由构建工具在底层自动处理。

## 代码实现

### 工程目录结构

```shell
DesugarTransform$ tree -L 2
.
|-- app
|   |-- build
|   |-- build.gradle.kts
|   |-- proguard-rules.pro
|   `-- src
|-- build-logic
|   |-- build
|   |-- build.gradle.kts
|   `-- src
|-- build.gradle.kts
|-- gradle
|   |-- libs.versions.toml
|   `-- wrapper
|-- gradle.properties
|-- gradlew
|-- gradlew.bat
|-- local.properties
`-- settings.gradle.kts
```

* app/build.gradle.kts
    ```kotlin
    plugins {
        alias(libs.plugins.android.application)
        id("com.example.desugar-transform")
    }

    android {
        namespace = "com.example.desugartransform"
        compileSdk = 36

        defaultConfig {
            applicationId = "com.example.desugartransform"
            minSdk = 29
            targetSdk = 36
            versionCode = 1
            versionName = "1.0"

            testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        }

        buildTypes {
            release {
                isMinifyEnabled = false
                proguardFiles(
                    getDefaultProguardFile("proguard-android-optimize.txt"),
                    "proguard-rules.pro"
                )
            }
        }
        compileOptions {
            sourceCompatibility = JavaVersion.VERSION_11
            targetCompatibility = JavaVersion.VERSION_11
        }
    }

    dependencies {

        implementation(libs.appcompat)
        implementation(libs.material)
        implementation(libs.activity)
        implementation(libs.constraintlayout)
        testImplementation(libs.junit)
        androidTestImplementation(libs.ext.junit)
        androidTestImplementation(libs.espresso.core)
    }
    ```
* DesugarTransform/build-logic/src/main/kotlin/com/example/gradle/plugin/DesugarTransformPlugin.kt
    ```kotlin
    package com.example.gradle.plugin

    import com.android.build.api.instrumentation.AsmClassVisitorFactory
    import com.android.build.api.instrumentation.ClassContext
    import com.android.build.api.instrumentation.ClassData
    import com.android.build.api.instrumentation.InstrumentationParameters
    import com.android.build.api.instrumentation.InstrumentationScope
    import com.android.build.api.variant.AndroidComponentsExtension
    import org.gradle.api.Plugin
    import org.gradle.api.Project
    import org.objectweb.asm.ClassVisitor
    import org.objectweb.asm.MethodVisitor
    import org.objectweb.asm.Opcodes
    import org.objectweb.asm.commons.AdviceAdapter

    /**
    * 一个 Gradle 插件，用于应用字节码转换。
    */
    abstract class DesugarTransformPlugin : Plugin<Project> {
        override fun apply(project: Project) {
            val androidComponents = project.extensions.getByType(AndroidComponentsExtension::class.java)

            androidComponents.onVariants { variant ->
                // **【错误修正】**
                // 简化插件注册，不再动态传递参数，以避免编译器解析错误。
                variant.instrumentation.transformClassesWith(
                    ReadAllBytesClassVisitorFactory::class.java,
                    InstrumentationScope.PROJECT
                ) {}
            }
        }
    }

    /**
    * **【错误修正】**
    * 工厂类不再需要自定义参数。我们使用 InstrumentationParameters.None。
    */
    abstract class ReadAllBytesClassVisitorFactory : AsmClassVisitorFactory<InstrumentationParameters.None> {

        override fun createClassVisitor(
            classContext: ClassContext,
            nextClassVisitor: ClassVisitor
        ): ClassVisitor {
            // **【错误修正】**
            // 直接为 ASM 提供一个稳定、兼容的 API 版本，而不是动态获取。
            // Opcodes.ASM9 是一个安全且现代的选择。
            return ReadAllBytesClassVisitor(Opcodes.ASM9, nextClassVisitor)
        }

        override fun isInstrumentable(classData: ClassData): Boolean {
            return true
        }
    }

    /**
    * 这个 ClassVisitor 会遍历一个类的所有方法。
    */
    private class ReadAllBytesClassVisitor(
        api: Int, // 参数现在直接就是 ASM API level
        classVisitor: ClassVisitor
    ) : ClassVisitor(api, classVisitor) { // 直接用于初始化父类

        override fun visitMethod(
            access: Int,
            name: String?,
            descriptor: String?,
            signature: String?,
            exceptions: Array<out String>?
        ): MethodVisitor {
            val originalMethodVisitor = super.visitMethod(access, name, descriptor, signature, exceptions)
            // 使用从父类继承的 'api' 字段
            return ReadAllBytesMethodVisitor(this.api, originalMethodVisitor, access, name, descriptor)
        }
    }

    /**
    * 这个 MethodVisitor 检查方法体内的每一条指令，并替换目标方法调用。
    */
    private class ReadAllBytesMethodVisitor(
        api: Int,
        methodVisitor: MethodVisitor,
        access: Int,
        name: String?,
        descriptor: String?
    ) : AdviceAdapter(api, methodVisitor, access, name, descriptor) {

        override fun visitMethodInsn(
            opcode: Int,
            owner: String?,
            name: String?,
            descriptor: String?,
            isInterface: Boolean
        ) {
            if (
                opcode == Opcodes.INVOKEVIRTUAL &&
                owner == "java/io/InputStream" &&
                name == "readAllBytes" &&
                descriptor == "()[B"
            ) {
                println("ASM-Transform: Replacing 'InputStream.readAllBytes()' call in method '${this.name}'")
                super.visitMethodInsn(
                    Opcodes.INVOKESTATIC,
                    "com/example/desugartransform/CompatInputStream",
                    "readAllBytes",
                    "(Ljava/io/InputStream;)[B",
                    false
                )
            } else {
                super.visitMethodInsn(opcode, owner, name, descriptor, isInterface)
            }
        }
    }

    ```

* DesugarTransform/build-logic/build.gradle.kts
    ```kotlin
    // 文件路径: build-logic/build.gradle.kts
    plugins {
        `kotlin-dsl`
    }

    // **【错误修正】**
    // 显式应用 'java' 插件，并配置 JVM toolchain。
    // 这将强制所有编译任务（Java 和 Kotlin）使用统一的 JDK 版本，
    // 从而解决因环境不一致导致的 API 解析错误。
    java {
        toolchain {
            languageVersion.set(JavaLanguageVersion.of(11))
        }
    }

    repositories {
        google()
        mavenCentral()
    }

    // 从主项目的根目录直接读取版本号。
    // 使用正确的相对路径来定位文件。
    val agpVersion = file("../gradle/libs.versions.toml").readLines()
        .first { it.trim().startsWith("agp =") }
        .substringAfter("=")
        .trim()
        .removeSurrounding("\"")

    dependencies {
        // 依赖 Android Gradle Plugin 的 API
        implementation("com.android.tools.build:gradle:$agpVersion")
        // 依赖 ASM 库用于字节码操作
        implementation("org.ow2.asm:asm-commons:9.6")
    }

    // 注册我们的插件，以便可以在 app 模块中通过 ID 使用它
    gradlePlugin {
        plugins {
            register("desugarTransform") {
                id = "com.example.desugar-transform"
                implementationClass = "com.example.gradle.plugin.DesugarTransformPlugin"
            }
        }
    }
    ```

* DesugarTransform/settings.gradle.kts

    ```kotlin
    pluginManagement {
        repositories {
            google {
                content {
                    includeGroupByRegex("com\\.android.*")
                    includeGroupByRegex("com\\.google.*")
                    includeGroupByRegex("androidx.*")
                }
            }
            mavenCentral()
            gradlePluginPortal()
        }
    }
    dependencyResolutionManagement {
        repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
        repositories {
            google()
            mavenCentral()
        }
    }

    rootProject.name = "DesugarTransform"
    include(":app")
    includeBuild("build-logic")
    ```

* DesugarTransform/app/src/main/java/com/example/desugartransform/CompatInputStream.java
    ```java
    // 1. 在 app 模块中创建兼容性辅助类
    // 文件路径: app/src/main/java/com/example/desugartransform/CompatInputStream.java

    package com.example.desugartransform;

    import android.util.Log;

    import java.io.ByteArrayOutputStream;
    import java.io.IOException;
    import java.io.InputStream;
    import java.util.Arrays;

    /**
     * 提供 InputStream.readAllBytes() 的向后兼容实现。
     */
    public final class CompatInputStream {

        private static final int DEFAULT_BUFFER_SIZE = 8192;

        // 私有构造函数，防止实例化
        private CompatInputStream() {}

        /**
         * 从输入流中读取所有剩余的字节。
         * @param is 要读取的输入流。
         * @return 包含流中所有字节的字节数组。
         * @throws IOException 如果发生 I/O 错误。
         */
        public static byte[] readAllBytes(InputStream is) throws IOException {
            Log.d("CompatInputStream","CompatInputStream readAllBytes");
            ByteArrayOutputStream bos = new ByteArrayOutputStream();
            byte[] buffer = new byte[DEFAULT_BUFFER_SIZE];
            int n;
            while ((n = is.read(buffer)) != -1) {
                bos.write(buffer, 0, n);
            }
            return bos.toByteArray();
        }
    }
    ```