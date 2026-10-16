# rgPDF

繁體中文 · [English](README.md)

正式應用程式名稱為 **rgPDF**，命令與 Python 套件名稱仍為 `rgpdf`。

rgPDF 是一套跨平台桌面工具，可使用純文字或規則表達式搜尋具有文字層的 PDF 與 Word 文件。每筆命中會在找到時立即顯示，並可在非同步頁面預覽中查看精確且可自訂顏色的螢光筆標示。

## 功能

- 可選擇搜尋 PDF、Word 文件（`.doc`、`.docx`）或兩者，並可選擇是否包含子資料夾。
- 支援純文字、規則表達式及區分大小寫。
- 支援跨行、跨頁匹配與行尾英文斷字合併。
- 每找到一筆結果就立即顯示，搜尋期間介面仍可操作。
- 檔案、命中段落與 PDF 頁面預覽三個連動區域。
- 逐字元反白座標與可自訂的螢光筆顏色。
- 繁體中文／英文介面，以及系統／淺色／深色主題。
- 保存搜尋與外觀偏好。

rgPDF 只搜尋 PDF 已有的文字層。Word 文件會先轉成快取 PDF，再沿用相同的搜尋與預覽流程；Windows 優先使用 Microsoft Word，其他情況則使用跨平台的 LibreOffice，搜尋 Word 時必須已安裝其中之一。啟動時會刪除 30 天未使用的轉換快取；快取超過 500 MB 時依最久未使用順序縮減，也可從工具列手動清除。rgPDF 不會執行文件巨集、不執行 OCR，也不修改來源檔案。

## 使用方式

「文件資料夾」下方的「主檔名篩選」可限制要搜尋的檔案，留空時不篩選。點擊輸入欄位左側的說明圖示，可像搜尋樣式欄位一樣開啟語法說明與範例。此欄位比對不含最後一個副檔名的完整主檔名，不區分大小寫；支援 `*`（任意字串）、`?`（單一字元）、`[abc]`、`[0-9]` 與 `[!abc]`。例如 `ch0*` 會包含 `ch01.pdf`、`ch02.docx`，排除 `ch1.pdf`、`ch2.docx`；`ch01` 則只比對完全相同的主檔名。篩選會在讀取 PDF 或轉換 Word 前執行，並搭配檔案類型與子資料夾設定；此欄位會保存至下次啟動，不受文字搜尋的 Regex 與區分大小寫設定影響。

預覽窗格的「上一頁／下一頁」會逐頁瀏覽整份文件，包含未命中頁；選取命中項目窗格中的其他段落即可跳至其命中頁面。「符合頁面」會依預覽區域的寬度與高度完整顯示整頁，並隨窗格大小調整；「符合寬度」則可用較大尺寸閱讀。

按「瀏覽」選取資料夾，輸入文字或規則表達式後按「搜尋」。選取檔案及命中段落即可查看頁面與螢光標示。下表依工具列由左至右排列；滑鼠停留可查看目前設定，三態按鈕每按一次切換一個狀態。

| 工具列圖示 | 功能 | 操作說明 |
| --- | --- | --- |
| <img src="docs/toolbar/recursive.png" width="34" alt="父子資料夾"> | 包含子資料夾 | 切換是否遞迴搜尋子資料夾。 |
| <img src="docs/toolbar/scope_pdf.png" width="34" alt="PDF"> <img src="docs/toolbar/scope_word.png" width="34" alt="Word"> <img src="docs/toolbar/scope_all.png" width="34" alt="PDF 與 Word"> | 搜尋檔案類型 | 循環切換 PDF → Word（DOC／DOCX）→ 兩者。搜尋 Word 需已有 Windows Microsoft Word 或 LibreOffice。 |
| <img src="docs/toolbar/case.png" width="34" alt="Aa"> | 區分大小寫 | 切換搜尋時是否區分大小寫。 |
| <img src="docs/toolbar/regex.png" width="34" alt="規則表達式"> | 規則表達式 | 切換 Regex；搜尋欄旁的說明圖示提供語法範例。 |
| <img src="docs/toolbar/highlighter.png" width="34" alt="螢光筆"> | 螢光筆顏色 | 選取預設色或自訂顏色。 |
| <img src="docs/toolbar/cache.png" width="34" alt="垃圾桶"> | 清除 Word 快取 | 確認後刪除轉換產生的 PDF，保留原始 Word 文件；搜尋期間停用。 |
| <img src="docs/toolbar/language_system.png" width="34" alt="系統語言"> <img src="docs/toolbar/language_zh.png" width="34" alt="中文"> <img src="docs/toolbar/language_en.png" width="34" alt="英文"> | 語言 | 循環切換跟隨系統 → 繁體中文 → English。 |
| <img src="docs/toolbar/theme_system.png" width="34" alt="系統配色"> <img src="docs/toolbar/sun.png" width="34" alt="淺色"> <img src="docs/toolbar/moon.png" width="34" alt="深色"> | 配色 | 循環切換跟隨系統 → 淺色 → 深色。 |
| <img src="docs/toolbar/about.png" width="34" alt="資訊"> | 關於 | 查看版本、授權與原始碼連結。 |

所有操作按鈕皆以圖示顯示；滑鼠停留時會顯示原本的中英文文字。搜尋、顏色設定與預覽按鈕如下：

| 圖示 | Tooltip／功能 |
| --- | --- |
| <img src="docs/toolbar/browse.png" width="34" alt="瀏覽…"> | 瀏覽… |
| <img src="docs/toolbar/search.png" width="34" alt="搜尋"> | 搜尋 |
| <img src="docs/toolbar/cancel.png" width="34" alt="取消"> | 取消 |
| <img src="docs/toolbar/help.png" width="34" alt="搜尋樣式說明"> | 搜尋樣式說明 |
| <img src="docs/toolbar/custom_color.png" width="34" alt="自訂顏色…"> | 自訂顏色… |
| <img src="docs/toolbar/previous_page.png" width="34" alt="上一頁"> | 上一頁 |
| <img src="docs/toolbar/next_page.png" width="34" alt="下一頁"> | 下一頁 |
| <img src="docs/toolbar/zoom_out.png" width="34" alt="縮小"> | 縮小 |
| <img src="docs/toolbar/zoom_in.png" width="34" alt="放大"> | 放大 |
| <img src="docs/toolbar/fit_width.png" width="34" alt="符合寬度"> | 符合寬度 |
| <img src="docs/toolbar/fit_page.png" width="34" alt="符合頁面"> | 符合頁面 |

搜尋設定會保存至下次啟動。啟動時會刪除 30 天未使用的轉換快取，若總量仍超過 500 MB，優先刪除最久未使用的項目。搜尋期間可按「取消」停止。

## 安裝最新版本

### Windows 免安裝版

從 [最新 GitHub Release](https://github.com/codemee/rgpdf/releases/latest)下載有版本編號的 `rgpdf-*-windows-x86_64.exe` 與對應 `.sha256` 檔。執行檔目前未簽章，因此 Windows SmartScreen 可能顯示未知發布者警告；選擇執行前，請先確認 SHA-256 與發布頁提供的值相同。

免安裝版不需要 Python 或 uv。搜尋 PDF 不需其他軟體；搜尋 Word 則需要 Windows 上既有的 Microsoft Word，或已安裝 LibreOffice。

### macOS App（Apple Silicon）

從[最新 GitHub Release](https://github.com/codemee/rgpdf/releases/latest)下載有版本編號的 `rgpdf-*-macos-arm64.dmg` 與對應 `.sha256` 檔。先核對下載檔：

```shell
shasum -a 256 rgpdf-*-macos-arm64.dmg
```

確認輸出與 `.sha256` 檔相同後，開啟 DMG，將 `rgpdf.app` 拖曳至 Applications。這個版本適用 Apple Silicon（M 系列）Mac，不需要安裝 Python 或 uv。

App 只有 ad-hoc 簽章且未經 Apple 公證。若 macOS 阻擋首次啟動，請在 Finder 的 Applications 中按住 Control 點按 `rgpdf`、選擇「打開」，再於確認視窗選擇「打開」。

### 使用 uv 安裝

先安裝 [uv](https://docs.astral.sh/uv/)，再從 PyPI 安裝最新發布版本：

```shell
uv tool install rgpdf
```

執行程式：

```shell
rgpdf
```

更新已安裝的版本：

```shell
uv tool upgrade rgpdf
```

支援 Windows 與 macOS，所需 Python 環境由 uv 管理。

若要直接從 GitHub 安裝最新原始碼發布版本，請使用會移動的 `latest` 標籤：

```shell
uv tool install "git+https://github.com/codemee/rgpdf.git@latest"
```

## 開發

```shell
git clone https://github.com/codemee/rgpdf.git
cd rgpdf
uv sync
uv run pytest
uv run rgpdf
```

本機開發使用 uv 執行測試與程式。執行檔與 App 統一在推送版本 tag 時由 GitHub Actions 遠端建置，不在本機建置。發布檔包含 Windows 單一執行檔、macOS Apple Silicon DMG、校驗檔及對應原始碼封存。

工具列圖示修改後，使用 `uv run python scripts/generate_toolbar_icons.py` 更新 README 圖片。

架構、匹配語意、並行處理與發布方式請參閱[技術細節](docs/TECHNICAL.zh-TW.md)，版本歷程請參閱[變更紀錄](CHANGELOG.zh-TW.md)。

## 發布版本

不可變的發布版本使用 `v0.0.3` 之類的版本標籤；可移動的 `latest` Git 標籤永遠指向最新的原始碼發布版本。PyPI 則提供標準的套件發布版本。

發布流程由 GitHub Actions 自動執行。確認 `pyproject.toml` 與 `src/rgpdf/__init__.py` 的版本一致並推送對應 tag：

```shell
git tag v0.0.8
git push origin v0.0.8
```

workflow 會平行測試並建置 Windows x86_64 與 macOS arm64，下載並驗證鎖定版本的第三方對應原始碼，建立同一個 GitHub Release、附加 SHA-256 校驗檔，最後透過 Trusted Publishing 發布至 PyPI。若任一測試、建置或來源驗證失敗，就不會建立 Release 或發布 PyPI。

## 授權

rgPDF 依 [GNU Affero General Public License version 3](LICENSE) 授權。你可以依該授權條款使用、研究、修改及重新散布本程式；散布執行檔時，必須同時提供該版本的完整對應原始碼。

本程式依 AGPLv3 使用 PyMuPDF/MuPDF，並依 LGPLv3 使用 PySide6/Qt。詳見[第三方授權聲明](THIRD-PARTY-NOTICES.md)與[發布授權檢查清單](docs/RELEASING.zh-TW.md)。
