+++
date = '2025-08-08T19:49:26+08:00'
draft = false
title = 'OEM Dynamic Theme Engine: A Multi-brand, Multi-user Technical Solution'
+++

# OEM 多品牌多使用者動態主題引擎技術方案

| 版本 | 日期 | 作者 | 修訂說明 |
| :---- | :---- | :---- | :---- |
| 2.18 | 2025-08-09 | Gemini | 在附錄中新增了“7.3 TMS 部署模式”的架構決策分析。 |
| **2.19** | **2025-08-09** | **Gemini** | **根據使用者提供的圖表，在 7.3 章節中新增了 TMS 部署模式的 PlantUML 對比圖。** |

## 1\. 方案概述 (Executive Summary)

本方案旨在為 OEM 廠商設計一套企業級的、功能完備的 Android 動態主題引擎。該引擎不僅能滿足多品牌、多 SKU 的出廠預設風格差異化，更能透過功能強大的**主題商店**，為使用者提供包括主題預覽、個性化微調、跨裝置同步在內的全方位個性化體驗。

方案核心是自研一個執行於 system\_server 的**主題管理服務 (ThemeManagerService, TMS)**，它作為主題生態的大腦，負責管理主題包的生命週期、處理多使用者環境下的權限與資料隔離、並向上層的**主題商店應用**提供穩定的 AIDL 介面。

最終目標是打造一個穩定、高效、安全且可擴展的主題平台，不僅能強化 OEM 品牌形象，更能構建一個開放的第三方主題生態，提升使用者體驗與黏性。

## 2\. 核心需求與目標

本方案旨在滿足以下 14 項核心需求：

| 編號 | 需求描述 | 關鍵目標 |
| :---- | :---- | :---- |
| 1 | **多品牌預設主題** | 實現不同產品線出廠時擁有獨特、固定的品牌視覺識別 (VI)。 |
| 2 | **動態主題切換** | 允許使用者在不重啟設備的情況下，一鍵下載、安裝、應用、刪除主題。 |
| 3 | **全域深度美化** | 主題效果需覆蓋系統框架、SystemUI、啟動器等多個核心應用，保證體驗一致性。 |
| 4 | **多使用者資料隔離** | 在多使用者模式下，每個使用者的主題選擇和私有主題列表應相互獨立，互不影響。 |
| 5 | **版本管理** | 支援主題的平滑升級與安全回滾，避免因版本問題導致系統不穩定。 |
| 6 | **第三方生態** | 建立標準化的主題包開發規範，允許第三方開發者參與主題製作與分發。 |
| 7 | **性能優化** | 主題切換應保證流暢快速，避免系統卡頓和耗電過快。 |
| 8 | **安全與權限控制** | 確保主題包來源可信，防止惡意主題破壞系統安全或洩露使用者隱私。 |
| 9 | **個性化主題定製** | 支援使用者對主題進行個性化定製，如調整顏色、字體、圖示樣式等。 |
| 10 | **跨裝置同步** | 支援使用者跨裝置同步主題設定，實現無縫體驗。 |
| 11 | **主題預覽功能** | 使用者可在應用前預覽主題效果，提升選擇體驗。 |
| 12 | **主題相容性檢測** | 自動檢測主題與系統版本、應用相容性，避免主題導致功能異常。 |
| 13 | **多語言支援** | 主題管理介面及主題包支援多語言，滿足全球使用者需求。 |
| 14 | **主題恢復預設設定** | 提供一鍵恢復系統預設主題的功能，方便使用者快速回退。 |

## 3\. 系統架構 (System Architecture)

整體架構以自研的 TMS 為核心，協同系統原生服務，向上層應用提供能力。

```planuml
@startuml  
' 相容性樣式設定  
skinparam defaultFontColor \#000000  
skinparam shadowing false  
skinparam package {  
    BorderColor \#555555  
    BackgroundColor \#FFFFFF  
}  
skinparam component {  
    BorderColor \#333333  
    BackgroundColor \#FFFFFF  
}  
skinparam database {  
    BorderColor \#BF360C  
    BackgroundColor \#FBE9E7  
}

package "OEM 雲服務" \#E3F2FD {  
    \[主題商店後端\] as Server  
    \[使用者帳戶與同步服務\] as AccountServer  
}

package "設備端" \#E0F2F1 {  
    package "應用層 (User)" {  
        \[主題商店 App (特權應用)\] as StoreApp  
    }

    package "框架層 (Framework)" {  
        \[ThemeManagerService (TMS, OEM自研)\] as TMS \#FFEB3B  
        \[OverlayManagerService (OMS)\] as OMS  
        \[PackageManagerService (PMS)\] as PMS  
        \[AssetManager\] as AssetMgr  
    }

    package "底層 (Native)" {  
        database "已安裝 RRO APKs" as RRO\_APKs  
    }

    package "資料儲存" {  
        database "主題資料庫 (SQLite)" as ThemeDB  
    }  
}

' 雲端與用戶端交互  
Server \<-down-\> StoreApp : (1) 下載主題包  
AccountServer \<.down.\> StoreApp : (10) 跨裝置同步

' 主題商店 App 呼叫主題管理服務  
StoreApp \<.down.\> TMS : (2) \[AIDL\] 業務請求，權限校驗

' 主題包安裝流程  
StoreApp \--\> TMS : (2a) 安裝/卸載主題包請求  
TMS \--\> PMS : (2b) 請求安裝/卸載主題 APK  
PMS \--\> TMS : (2c) 返回安裝/卸載結果  
TMS \--\> ThemeDB : (2d) 更新主題元資料  
TMS \--\> OMS : (2e) 啟用/停用對應的 RRO

' 主題啟動與資源訪問流程  
TMS .down.\> PMS : (3) 監聽 APK 狀態  
TMS .down.\> OMS : (4) 核心啟用/停用 RROs  
TMS .down.\> ThemeDB : (5) 讀寫主題元資料

OMS .down.\> AssetMgr : (6) 透過資源管理訪問 RRO 資源  
AssetMgr .down.\> RRO\_APKs : (7) 讀取已安裝的 RRO APK 檔案

@enduml
```

![系统架构图](/ethenslab/images/android-thememanagerservice-sw-architecture.png)

## 4\. 核心功能模組設計

### 4.1. 主題包規範 (Theme Package Specification)

一個邏輯上的「主題包」是使用者從商店下載和安裝的基本單元，通常以 **ZIP 壓縮包**的形式分發。它內部包含了一系列獨立的 RRO APK 和描述其元資料的清單檔案，以確保主題的完整性、安全性及管理的便捷性。

* **分發格式**:  
  * 推薦使用 .zip 格式，便於統一管理和分發。  
  * ZIP 包內應包含：  
    * **多個 RRO APKs**: 每個 APK 針對一個目標應用（如 framework-res.apk, systemui.apk）。  
    * **清單檔案 (manifest.json)**: 描述整個主題包的元資料，供主題商店 App 解析。  
    * **預覽資源 (previews/)**: 包含鎖屏、桌面等預覽圖的資料夾。  
* 安全性與完整性校驗 (MD5):  
  為確保主題包在下載、解壓和安裝過程中的安全，推薦採用雙重 MD5 校驗機制。  
  1. **ZIP 包整體校驗**: 主題商店伺服器在提供下載時，應同時提供整個 ZIP 包的 MD5 值。商店 App 下載完成後，需先對 ZIP 檔案進行 MD5 校驗，確保下載過程完整無誤。  
  2. **內部 RRO APK 校驗**: manifest.json 檔案中，需包含每個 RRO APK 的獨立 MD5 值。商店 App 在解壓 ZIP 包後、安裝任何 APK 之前，必須逐一校驗每個 RRO APK 的 MD5 值，確保檔案未被篡改。  
* 主題包清單 (manifest.json) 規範:  
  此檔案是主題商店 App 理解主題包內容的核心。  
  {  
    "themeId": "com.oem.theme.deepblue",  
    "themeName": "深海藍",  
    "author": "OEM Design Team",  
    "versionName": "1.2.0",  
    "description": "一款靜謐的深藍色主題。",  
    "zipMd5": "0123456789abcdef0123456789abcdef",  
    "rroApks": \[  
      {  
        "file": "framework-res.apk",  
        "target": "android",  
        "md5": "a1b2c3d4e5f678901234567890abcdef"  
      },  
      {  
        "file": "systemui.apk",  
        "target": "com.android.systemui",  
        "md5": "fedcba09876543210987654321fedcba"  
      }  
    \]  
  }

* RRO APK Manifest 規範:  
  每個獨立的 RRO APK 必須遵循以下規範：  
  * \<overlay android:targetPackage="包名" /\>: **必須**聲明，且每個 RRO APK 只能有一個。  
  * android:versionCode: **必須**，用於版本管理。  
  * \<uses-sdk android:minSdkVersion="..." /\>: **必須**，用於相容性檢測。  
  * \<meta-data\>: **建議**增加自定義元資料，包括：  
    * com.oem.theme.name: 主題名（可指向 @string/ 實現多語言）。  
    * com.oem.theme.author: 作者名。  
    * com.oem.theme.preview\_assets: 指向主題預覽圖資源。  
    * com.oem.theme.is\_customizable: (布林值) 聲明是否支援個性化定製。

### 4.2. 編譯時靜態覆蓋層 (需求 \#1)

此模組是實現品牌差異化的基礎，負責定義設備的出廠預設風格。

* **技術**: 採用 AOSP 標準的**編譯時資源覆蓋 (Build-time Resource Overlay)**。  
* **實現**:  
  1. **建立 Overlay 目錄**: 在 AOSP 原始碼的 device/ 目錄下，為每個品牌或產品線建立獨立的 Overlay 目錄結構。  
  2. **覆寫資源**: 在各自的 Overlay 目錄中，建立與 frameworks/base/core/res/ 相同的子目錄結構，並放置需要覆寫的資源檔案。核心是覆寫 themes\_device\_defaults.xml 來定義品牌專屬的 Theme.DeviceDefault 主題。  
  3. **配置編譯腳本**: 在對應產品線的 .mk 編譯腳本中，透過 PRODUCT\_PACKAGE\_OVERLAYS 變數指向該品牌專屬的 Overlay 目錄。  
* **目的**: 確保不同產品線在編譯時，其韌體就包含了各自獨特的品牌基因。這是所有後續動態主題的「回退」基準。

### 4.3. 主題管理服務 (ThemeManagerService \- TMS)

作為 system\_server 的核心服務，是所有主題業務邏輯的中樞。

* 內部工作時序圖:  
  下圖展示了 TMS 在系統啟動時的初始化流程，以及處理主題安裝和應用請求的內部交互過程。  
  ```plantuml
  @startuml  
  ' 相容性樣式設定  
  skinparam defaultFontColor \#000000  
  skinparam shadowing false  
  skinparam sequence {  
      LifeLineBorderColor \#555555  
      ParticipantBorderColor \#555555  
      ArrowColor \#333333  
  }

  participant "SystemServer" as SS  
  participant "ThemeManagerService\\n(TMS)" as TMS  
  participant "PackageManagerService\\n(PMS)" as PMS  
  participant "Theme Store App" as StoreApp  
  participant "OverlayManagerService\\n(OMS)" as OMS  
  database "ThemeDB" as DB

  group 系統啟動初始化  
      SS \-\> TMS: 建構並啟動服務  
      activate TMS  
      TMS \-\> PMS: 註冊廣播接收器\\n(監聽 APK 安裝/卸載/升級)  
      TMS \-\> DB: 載入主題資料到記憶體  
  end

  group 主題安裝請求 (installTheme)  
      StoreApp \-\> StoreApp: 下載並解壓 Theme.zip  
      StoreApp \-\> StoreApp: \*\*透過 FileProvider 產生 RRO APKs 的 Uri 列表\*\*  
      StoreApp \-\> TMS: \[AIDL\] installThemeForUser(apkUris, userId)  
      TMS \-\> TMS: 權限校驗 & 安全校驗  
      loop 對每個 Uri  
          TMS \-\> PMS: 請求安裝 RRO APK (傳入 Uri)  
          activate PMS  
          PMS \--\> TMS: 返回安裝結果  
          deactivate PMS  
      end  
      alt 所有 RROs 安裝成功  
          TMS \-\> DB: 將新主題元資料寫入資料庫  
          TMS \--\> StoreApp: 返回安裝成功  
      else 部分 RROs 安裝失敗  
          TMS \-\> PMS: 請求卸載已安裝的 RROs (回滾)  
          TMS \--\> StoreApp: 返回安裝失敗  
      end  
  end

  group 主題應用請求 (applyTheme)  
      StoreApp \-\> TMS: \[AIDL\] applyThemeForUser("ThemeB", userId)  
      TMS \-\> TMS: 權限校驗  
      TMS \-\> DB: 查詢當前主題 (ThemeA) 的 RROs  
      TMS \-\> OMS: 迴圈停用 ThemeA 的所有 RROs  
      TMS \-\> DB: 查詢新主題 (ThemeB) 的 RROs  
      TMS \-\> OMS: 迴圈啟用 ThemeB 的所有 RROs  
      TMS \-\> DB: 更新 userId 的當前主題為 ThemeB  
      TMS \--\> StoreApp: 返回操作結果  
  end  
  deactivate TMS  
  @enduml
  ```
  
  ![](/ethenslab/images/android-thememanagerservice-sw-architecture.png)

* AIDL 介面與 Parcelable 實現:  
  為實現模組化和資料傳輸，需要定義 AIDL 介面及相關的 Parcelable 資料類型。
  ```java
  **IThemeManagerService.aidl** (核心服務介面)  
  // file: com/oem/themes/IThemeManagerService.aidl  
  package com.oem.themes;

  import android.net.Uri;  
  import com.oem.themes.ThemeInfo;  
  import com.oem.themes.CustomizationRequest;

  interface IThemeManagerService {  
      boolean installThemeForUser(in List\<Uri\> apkUris, int userId);  
      List\<ThemeInfo\> getThemeListForUser(int userId);  
      ThemeInfo getThemeInfoForUser(String themeId, int userId);  
      boolean applyThemeForUser(String themeId, int userId);  
      ThemeInfo getAppliedThemeForUser(int userId);  
      boolean rollbackTheme(String themeId, int userId);  
      boolean deleteThemeForUser(String themeId, int userId);  
      boolean applyCustomization(in CustomizationRequest request, int userId);  
      boolean clearCustomization(int userId);  
      boolean restoreDefaultTheme(int userId);  
  }
  ```

### 4.4. 主題預覽機制 (需求 \#11)

在「主題商店 App」內部的沙盒環境中實現，避免對系統進行實際的 RRO 覆蓋。

* **技術**: 核心是**跨 APK 載入資源**。  
* **流程**:  
  1. 在商店 App 中建立 PreviewActivity，其佈局模擬真實系統介面。  
  2. 透過 Context.createPackageContext() 建立指向目標 RRO APK 的 Context。  
  3. 利用此 Context 安全地載入 RRO APK 中的資源（顏色、圖示等），並手動應用到 PreviewActivity 的模擬控制項上。

### 4.5. 個性化主題定製 (需求 \#9)

此功能旨在允許使用者在不重新安裝完整主題包的情況下，對當前主題的特定參數（如顏色、字體）進行微調。鑑於在設備端動態產生並簽署 APK 的複雜性和安全風險，本方案提出以下三種業界主流的備選實現路徑。

* **方案 A (推薦): 參數驅動框架 (Parameter-Driven Framework)**  
  * **核心思想**: 將「主題」的概念從靜態的資源包，轉變為由一組動態參數驅動。這是 MIUI、OneUI 等成熟主題引擎的典型做法。  
  * **實現**:  
    1. **修改框架**: 深度定製 Android Framework 的核心資源載入邏輯（AssetManager / ResourcesImpl）。使其在載入指定資源（如 R.color.accent\_color）時，**優先**檢查一個由 TMS 管理的參數表（例如 /data/system/theme\_params.xml）。  
    2. **參數更新**: 當使用者在主題商店中調整顏色時，商店 App 透過 TMS 的 applyCustomization 介面，僅僅是更新這個 XML 參數表中的一個鍵值對。  
    3. **即時生效**: 下一次任何應用請求該資源時，AssetManager 會直接讀取並返回參數表中的新值，無需重新安裝任何 APK，也無需重啟應用。  
  * **優點**: 極為靈活強大，支援任意參數的即時調整，性能開銷小。  
  * **缺點**: 對 Framework 的修改最深入，開發和維護成本最高。  
* **方案 B (備選): 預編譯 RRO 組合 (Pre-compiled RRO Combination)**  
  * **核心思想**: 預先為有限的定製選項製作多套 RROs，透過啟用/停用不同的 RRO 組合來實現個性化。這是 AOSP 動態色彩 (Monet) 和 Pixel Themes 的實現方式。  
  * **實現**:  
    1. **預製 RROs**: 在編譯時，為每種可定製的顏色（如 10 種）和字體（如 5 種）都製作一個獨立的、只包含該項資源的 RRO APK。  
    2. **組合切換**: 當使用者選擇「藍色」+「Roboto 字體」時，TMS 會呼叫 OMS，**啟用** blue\_color.apk 和 roboto\_font.apk，同時**停用**其他所有顏色和字體的 RROs。  
  * **優點**: 對 Framework 無侵入式修改，完全利用原生 RRO 機制，切換速度快。  
  * **缺點**: 靈活性有限，只能在預設的選項中選擇；如果組合過多，會佔用較多的儲存空間。  
* **方案 C (特定場景): 外部資源載入 (External Asset Loading)**  
  * **核心思想**: 將可變資源（如圖示、桌布）打包成獨立的非 APK 資料檔案（如 ZIP），由特定應用在執行時自行載入。  
  * **實現**:  
    1. **修改目標應用**: 需要修改 SystemUI、Launcher 等自家應用的程式碼，讓它們在啟動時檢查 TMS 指定的外部資源包路徑，並優先載入其中的資源。  
    2. **TMS 職能**: TMS 負責管理這些外部資源包的路徑和版本。  
  * **優點**: 繞過了 RRO 機制，更新靈活。  
  * **缺點**: **無法影響第三方應用**，只能用於自家應用的深度定製。

### 4.6. 跨裝置同步 (需求 \#10)

* **後端**: 需要 OEM 雲服務提供使用者帳戶系統和主題同步資料庫，記錄使用者購買和應用的主題。  
* **設備端**:  
  1. **主題商店 App** 負責使用者登入和與雲端同步。  
  2. 當使用者在新設備上登入時，商店 App 從雲端拉取其主題列表。  
  3. 如果雲端記錄的主題在本地尚未安裝，商店 App 會提示或自動下載安裝。  
  4. 安裝完成後，商店 App 呼叫 TMS 的 applyThemeForUser() 介面，應用使用者在雲端記錄的主題，實現無縫體驗。

### 4.7. 相容性檢測與恢復預設 (需求 \#12, \#14)

* **相容性檢測**:  
  * **安裝時**: TMS 監聽到 ACTION\_PACKAGE\_ADDED 後，會解析 RRO APK 的 minSdkVersion，若不滿足當前系統版本，則在資料庫中將其標記為「不相容」，商店 App 中不予顯示。  
  * **系統升級後**: 開機時，TMS 會重新校驗所有已安裝主題的相容性。  
* **恢復預設**:  
  * **TMS 實現**: restoreDefaultTheme(userId) 介面的核心邏輯是：查詢該使用者當前所有**已啟用**的 RROs，並呼叫 OMS.setEnabled(..., false) 將它們**全部停用**。  
  * **效果**: 當所有動態 RROs 都被停用後，系統會自動回退到由**編譯時靜態 Overlay** 定義的出廠預設主題。

## 5\. 安全、性能與多語言 (需求 \#7, \#8, \#13)

* **安全與權限控制**:  
  * **簽署校驗**: 所有主題包（尤其第三方）必須經過簽署校驗。  
  * **權限隔離**: TMS 的 AIDL 介面必須進行嚴格的權限檢查，只允許擁有平台簽署的商店 App 呼叫。  
  * **安裝來源**: 可限制只有主題商店 App 才有權安裝 RRO 類型的 APK。  
* **性能優化**:  
  * **非同步處理**: 所有 TMS 的耗時操作（資料庫、檔案 IO、動態 RRO 產生）都必須在工作執行緒中進行。  
  * **智慧刷新**: 應用主題後，應按需、精準地刷新受影響的 UI 進程，而不是粗暴地重啟整個系統。  
* **多語言支援**:  
  * **主題商店 App**: 自身 UI 需支援多語言。  
  * **主題包**: 鼓勵開發者在 RRO APK 的 res/ 目錄下提供多語言的字串資源 (values-en, values-ja 等)，主題名、描述等都應使用 @string/ 引用。

## 6\. 總結

本方案 v2.17 在原有基礎上進行了全面擴充和修正，形成了一套覆蓋從出廠定製到使用者個性化微調、從本地管理到雲端同步的全鏈路企業級主題引擎解決方案。方案在保持架構穩定性的同時，為所有 14 項核心需求提供了具體、可行的技術實現路徑，能夠有力支撐 OEM 廠商打造差異化、高黏性的使用者體驗。

## 7\. 附錄：架構決策 (Appendix: Architectural Decisions)

### 7.1. 檔案傳遞機制：FileProvider vs. 共享目錄

* **問題**: 主題商店 App (應用層) 如何安全地將解壓後的 RRO APK 檔案傳遞給 ThemeManagerService (框架層) 進行安裝？  
* **方案 A (不推薦): 共享目錄**  
  * **描述**: 在 /data 下建立一個雙方都能讀寫的「公共」目錄。  
  * **弊端**:  
    1. **嚴重安全風險**: 破壞了 Android 的應用沙盒模型。  
    2. **違反 SELinux 策略**: 需要修改系統核心的 SELinux 策略，為 system\_server 和應用進程開設一個不安全的訪問通道，這會削弱整個系統的安全性。  
* **方案 B (推薦): FileProvider \+ Uri 授權**  
  * **描述**: 主題商店 App 將 APK 檔案放在自己的私有目錄，並透過 FileProvider 產生一個臨時的、帶授權的 content:// Uri。TMS 接收這個 Uri，並憑藉此次 IPC 呼叫獲得的臨時授權來讀取檔案。  
  * **優點**:  
    1. **安全**: 遵循 Android 官方推薦的標準，無需修改 SELinux，保證了沙盒的完整性。  
    2. **最小權限**: 授權是臨時的、針對特定檔案的，TMS 無法訪問商店 App 的任何其他私有檔案。  
    3. **相容性好**: 能夠平滑適配未來 Android 版本的安全更新。  
* **結論**: 為保證系統的安全性和穩定性，本方案**明確採用 FileProvider \+ Uri 授權**的機制進行跨進程檔案傳遞。

### 7.2. 個性化定製實現方案選型

* **問題**: 如何在不進行設備端 APK 簽署的情況下，實現使用者對主題參數的即時調整？  
* **方案 A (推薦 \- 功能強大): 參數驅動框架**  
  * **描述**: 修改 AssetManager，使其載入資源時優先讀取一個由 TMS 管理的參數檔案。使用者定製時只修改此檔案。  
  * **優點**: 極度靈活，支援任意參數即時調整，性能開銷小。  
  * **缺點**: 對 Framework 修改最深入，開發和維護成本最高。  
* **方案 B (推薦 \- 簡單穩定): 預編譯 RRO 組合**  
  * **描述**: 預製多套針對不同參數（如顏色）的 RRO APKs，使用者定製時，TMS 負責啟用/停用正確的 RRO 組合。  
  * **優點**: 對 Framework 無侵入式修改，完全利用原生 RRO 機制，穩定且切換快。  
  * **缺點**: 靈活性有限，只能在預設選項中選擇，組合多時佔用儲存空間。  
* **結論**: 對於追求極致個性化和靈活性的主題引擎，**方案 A 是最佳選擇**。對於追求實現簡單、風險可控的場景，**方案 B 是一個非常穩健的備選方案**。本方案的設計允許 TMS 在底層實現時，根據產品需求選擇其中一種或混合使用。

### 7.3. TMS 部署模式：核心服務 vs. 應用內實現

* **問題**: ThemeManagerService 的邏輯應該部署在 system\_server 核心服務中，還是直接在主題商店 App 內部實現？  
* **架構對比圖**: 
  ```plantuml
  @startuml  
  skinparam shadowing false  
  skinparam defaultFontColor \#000000  
  skinparam package {  
      BorderColor \#555555  
      BackgroundColor \#FFFFFF  
  }  
  skinparam rectangle {  
      BorderColor \#333333  
      BackgroundColor \#FFFFFF  
  }

  title TMS 架构方案对比

  ' 左边：system\_server 方案  
  package "方案 A：TMS 在 framework 层（system\_server）" \#E3F2FD {  
      rectangle "应用层\\n- 主题商店 App（前端 UI）\\n- 其他授权主题客户端" as A\_App  
      rectangle "Framework 层\\n- ThemeManagerService (TMS)\\n- OverlayManagerService (OMS)\\n- PackageManagerService (PMS)" as A\_FW  
      rectangle "数据存储\\n- 主题数据库 (ThemeDB)\\n- 已安装 RRO APKs" as A\_DB

      A\_App \--\> A\_FW : AIDL 调用  
      A\_FW \--\> A\_DB : 读写主题元数据 / 访问 RRO  
  }

  note right of A\_FW  
  \*\*优点：\*\*  
  \- 安全隔离彻底（system\_server）  
  \- 公共 API 可复用给多 App  
  \- 生命周期与系统一致，极稳定  
  \*\*缺点：\*\*  
  \- 迭代慢，需 OTA  
  \- IPC 有一定性能开销  
  \- 开发维护成本高  
  end note

  ' 右边：App 集成方案  
  package "方案 B：TMS 集成在主题商店 App 内" \#E0F2F1 {  
      rectangle "主题商店 App（包含 TMS 模块）\\n- UI 展示\\n- 主题管理逻辑\\n- 调用系统服务（OMS / PMS）" as B\_App  
      rectangle "Framework 层\\n- OverlayManagerService (OMS)\\n- PackageManagerService (PMS)" as B\_FW  
      rectangle "数据存储\\n- 主题数据库 (ThemeDB)\\n- 已安装 RRO APKs" as B\_DB

      B\_App \--\> B\_FW : 直接系统 API 调用  
      B\_App \--\> B\_DB : 读写主题元数据 / 访问 RRO  
  }

  note right of B\_App  
  \*\*优点：\*\*  
  \- 迭代快（应用更新即可）  
  \- 架构简单，无需额外系统服务  
  \- 性能更好（减少一次 IPC）  
  \*\*缺点：\*\*  
  \- 安全性依赖 App 权限  
  \- 仅限单一商店使用  
  \- 商店 App 崩溃可能影响体验  
  end note

  @enduml
  ```
  ![](/ethenslab/images/tms-solution-comparison.png)

* **结论**: 儘管方案 A 在特定場景下可行，但為了構建一個**安全、穩定且具備長期擴展性**的企業級主題生態，本方案**明確推薦並採用方案 B (核心服務)**。