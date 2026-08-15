# rgpdf 技術細節

繁體中文 · [English](TECHNICAL.md)

## 技術與模組邊界

rgpdf 支援 Python 3.12–3.13，並由 uv 管理。PySide6 提供桌面介面，PyMuPDF 負責 PDF 文字抽取與頁面渲染，第三方 `regex` 套件則提供 Unicode 規則表達式與單檔逾時限制。

| 模組 | 職責 |
| --- | --- |
| `app.py` | QApplication 生命週期、調色盤、扁平樣式與啟動流程 |
| `main_window.py` | 搜尋控制、設定工具列、漸進式結果模型與畫面連動 |
| `search.py` | 檔案探索、PDF 抽取、正規化、比對及座標映射 |
| `worker.py` | 背景搜尋工作與跨執行緒 Qt signal |
| `preview.py` | 非同步頁面渲染、過時請求淘汰、縮放與螢光筆 |
| `models.py` | 不可變搜尋選項、結果、頁面反白與抽取映射 |
| `i18n.py` | 英文與繁體中文文字目錄 |
| `resources.py` | 封裝後的應用程式圖像資源查找 |

搜尋核心不依賴 UI widget，因此可由測試或其他 Python 呼叫端獨立使用。

## 搜尋管線

1. `discover_pdfs` 依穩定的相對路徑順序列舉 `.pdf`，是否遞迴由 `SearchOptions.recursive` 控制。
2. 每份 PDF 獨立開啟；加密、損壞、空白或沒有文字層的檔案會成為不中斷搜尋的警告。
3. 每頁透過 PyMuPDF `rawdict` 抽取，並明確停用 `TEXT_PRESERVE_IMAGES`，避免搜尋文字時解碼圖片資料。
4. 依閱讀順序走訪文字區塊、行、span 與字元，每個可見字元都保存頁碼與精確 bounding box。
5. 行內空白會合併，一般換行與頁面邊界轉成空格；若行尾是連字號，會先移除再接續下一行。
6. 在完整正規化文件上搜尋。純文字會先跳脫；規則表達式採 Unicode `VERSION1`、可選完整大小寫折疊，以及單檔逾時。
7. 忽略零寬度命中；其他命中只映射實際涵蓋字元的方框。
8. 段落摘要以最近的中英文標點（`，。！？；：、,.!?;:`）為界；沒有標點時才使用有限字數與省略號。

正規化文字與 `CharacterRef` tuple 的長度永遠相同。人工加入的分隔空格帶有頁面參照但沒有方框，因此規則表達式可以跨頁，又不會產生不存在的反白區域。

## 漸進結果與並行處理

`SearchWorker` 在 Qt 全域 thread pool 中執行 `search_folder`。搜尋核心建立每個 `TextMatch` 後立即呼叫 callback，worker 再透過 `match_found` 傳給主執行緒；主執行緒新增該列、更新所屬檔案筆數，並保留現有選取項目。

預覽渲染與搜尋彼此獨立。每次選取會建立 `PreviewRenderWorker`，使用自己的文件 handle 開啟 PDF，在 UI 執行緒之外渲染成 `QImage` 並畫上半透明反白。單調遞增的 request ID 會淘汰較舊的選取或縮放結果；只有轉換成 `QPixmap` 與更新 widget 在 UI 執行緒進行。

取消搜尋使用 thread-safe event，並在文件之間檢查。Regex 另有逾時限制，防止災難性回溯。關閉視窗時會讓待處理預覽失效，並要求取消搜尋。

## 介面與保存設定

主畫面使用頂端設定工具列與水平 splitter：

- 左側：上方是資料夾／樣式，下方是檔案與命中結果表。
- 右側：完整高度的 PDF 預覽、命中頁切換、符合寬度與縮放。

設定使用 `QSettings("rgpdf", "rgpdf")`：

| Key | 意義 |
| --- | --- |
| `appearance/language` | `system`、`zh_TW` 或 `en` |
| `appearance/theme` | `system`、`light` 或 `dark` |
| `appearance/highlight_color` | `#rrggbb` 螢光筆顏色 |
| `search/folder` | 上次選取的資料夾 |
| `search/pattern` | 上次搜尋樣式 |
| `search/use_regex` | 規則表達式模式 |
| `search/case_sensitive` | 區分大小寫 |
| `search/recursive` | 包含子資料夾 |
| `window/geometry` | 視窗位置與大小 |
| `window/main_splitter` | 左側／預覽比例 |
| `window/result_splitter` | 檔案／命中項目比例 |

語言與主題按鈕各自循環三種模式；切換設定使用中性色的啟用樣式。螢光筆按鈕只有筆形圖示使用所選顏色，色彩面板提供常用色與原生 `QColorDialog`。

## 測試與封裝

測試涵蓋純文字與 Regex、大小寫、跨頁映射、斷字合併、標點摘要、損壞／無文字 PDF、逐筆 callback、設定保存、主題切換、封裝 SVG 讀取與非同步預覽。

```shell
uv sync
uv run pytest
uv build
```

`uv build` 會產生 sdist 與 wheel。SVG 程式圖示存放在 Python package 內，因此 editable 與正式建置都能透過 `importlib.resources` 取得。

## 發布流程

1. 在 `pyproject.toml` 與 `src/rgpdf/__init__.py` 設定相同版本。
2. 行為變更時同步更新中英文變更紀錄、README 與技術文件。
3. 執行測試與 `uv build`。
4. 提交到 `main`，建立不可變的 `vX.Y.Z` 標籤並發布對應 GitHub Release。
5. GitHub Release 事件會執行 `.github/workflows/publish-pypi.yml`，建置兩種發布檔並透過 Trusted Publishing 發布到 `pypi` environment。
6. 將 `latest` 標籤強制移到相同 commit，再用 `git push origin refs/tags/latest --force` 推送。

安裝文件必須使用 PyPI 的最新發布版本或會移動的 `latest` 原始碼標籤，不得寫死版本標籤；不可變版本標籤則保留給可重現的原始碼 checkout 與發布歷程。PyPI 專案必須信任儲存庫 `codemee/rgpdf`、工作流程 `publish-pypi.yml` 與 environment `pypi`，GitHub 不保存長效上傳 token。
