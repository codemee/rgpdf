# Rust 改寫可行性評估

繁體中文 · [English](RUST_FEASIBILITY.md)

以 rgPDF 0.1.10 為基準，查核日期為 2026-11-08。這是研究與遷移建議，尚未實作 Rust 版本，也沒有 Rust 版本的實測效能數據。

完整改寫在技術上可行，但需要重建 GUI 與系統整合，不是逐行翻譯 Python。主要驗收條件是 Windows 單一 EXE、macOS 支援、等價文字／座標行為、Regex 相容性，以及多標籤搜尋配合序列 Word 轉檔。

| 範圍 | 候選方案 | 主要工作／風險 |
| --- | --- | --- |
| 桌面介面 | egui/eframe 或 Slint | 重建標籤、表格、分隔窗格、tooltip、焦點、剪貼簿、文字選取、中文輸入與自訂圖示，驗證兩平台。CXX-Qt 可整合 Rust／Qt，但仍有 Qt 部署問題。 |
| PDF | 優先 mupdf-rs，備選 pdfium-render | MuPDF 可沿用目前引擎家族，支援渲染、密碼與定位／結構化文字；仍需保留閱讀順序、逐字座標、旋轉／裁切、TrimBox 與表格接合。PDFium 換了引擎，需重新建立相容性基準。 |
| Regex | regex 搭配明確選定的進階引擎，或 PCRE2／fancy-regex | Rust regex 不支援目前會使用的 look-around／反向參照。候選方案都不保證等同 Python regex 的 FULLCASE／VERSION1，必須保留預設多行、完整單字及執行限制。 |
| Word | Windows 使用 windows-rs COM；其他平台執行 LibreOffice | 移植 STA 生命週期、唯讀開啟、停用巨集、取消與逐一轉換。Rust 不會消除外部轉檔需求，也不保證加快 Word 匯出。 |
| 工作／設定／OS | Rust 工作執行緒、channel 與平台 API | 保留各頁狀態、共用轉檔佇列、取消、PDF 密碼提示、Explorer／Finder 與設定遷移。 |

單一 EXE 取決於完整依賴鏈，不能只換成 Rust 就消除動態 PDF／GUI DLL。pdfium-render 支援靜態連結，但不會代為建置或提供靜態 PDFium。需先證明 MuPDF／PDFium 靜態連結、Windows CRT 連結方式、資源內嵌與乾淨機器測試都可行。檔案大小及啟動速度必須實測；OS 外部掃描仍可能造成等待。

Rust regex 回傳 UTF-8 位元組位置，Python 目前的字元座標表使用字串字元索引。必須建立 Regex 位置到字形／頁面座標的明確對應，涵蓋中文與組合字元；直接照搬索引會造成螢光標示偏移。進階引擎的回溯限制也不等同 Python 的牆鐘時間 timeout，若需硬性期限，仍應保留可取消的工作程序邊界。

建議驗證順序：

1. 先產出不依賴 Python 的 Windows 單一 EXE 與 macOS App，能開啟使用者實際 PDF、擷取逐字座標及渲染頁面，確認中文字型與密碼。
2. 重現 F6791_CH06(30).pdf 的行首 33 筆／不限行首 34 筆，與 Python 基準比對命中文字、頁碼及矩形。另涵蓋斷字、表格界線、完整單字、捕捉群組與 Unicode。
3. 建立縮放、TrimBox、滑鼠選字複製及 PNG 剪貼簿的小型檢視器，評估 Slint／egui 與中文輸入。
4. 加入單一 Word 轉換佇列及並行搜尋，再移植完整 UI、工作階段、OS 整合與現有測試。

若目標是這次啟動問題，只改 Rust 快取啟動器的範圍小得多，能保留既有 Python 功能及驗證結果。現有快取分支先用 Windows .NET Framework 原型驗證快取本身，不等於 Rust 改寫。若長期目標是移除 Python／Qt 並改變部署方式，完整 Rust App 才更值得投入。兩者範圍不同，目前都還沒有本專案的 Rust 效能實測。

第一手來源：[mupdf-rs](https://github.com/messense/mupdf-rs)、[pdfium-render 靜態連結](https://github.com/ajrcarey/pdfium-render#static-linking)、[egui](https://github.com/emilk/egui)、[Slint](https://github.com/slint-ui/slint)、[CXX-Qt](https://github.com/KDAB/cxx-qt)、[Rust regex](https://github.com/rust-lang/regex)、[位元組索引](https://docs.rs/regex/latest/regex/struct.Match.html)、[fancy-regex](https://github.com/fancy-regex/fancy-regex)、[PCRE2 Rust bindings](https://github.com/BurntSushi/rust-pcre2)、[windows-rs](https://github.com/microsoft/windows-rs)。
