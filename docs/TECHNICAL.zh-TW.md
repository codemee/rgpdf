# rgPDF 技術細節

繁體中文 · [English](TECHNICAL.md)

## 技術與模組邊界

rgPDF 支援 Python 3.12–3.13，並由 uv 管理。PySide6 提供桌面介面，PyMuPDF 負責 PDF 文字抽取與頁面渲染，第三方 `regex` 套件則提供 Unicode 規則表達式與單檔逾時限制。Windows 建置使用 pywin32，要求既有的 Microsoft Word 執行固定格式匯出。

| 模組 | 職責 |
| --- | --- |
| `app.py` | QApplication 生命週期、調色盤、扁平樣式與啟動流程 |
| `buttons.py` | 共用且配合主題的向量操作按鈕、中英文 tooltip 與無障礙名稱 |
| `main_window.py` | 搜尋控制、設定工具列、漸進式結果模型與畫面連動 |
| `search.py` | 檔案探索、轉換分派、PDF 抽取、正規化、比對及座標映射 |
| `preparation.py` | 資料夾背景轉檔、動態待轉清單及搜尋共用結果 |
| `word_conversion.py` | Word／LibreOffice 轉換器選擇與本機 PDF 快取 |
| `worker.py` | 背景搜尋工作與跨執行緒 Qt signal |
| `pdf_search_process.py` | 可重用的 PDF 搜尋子程序、逐筆命中 IPC 與取消清理 |
| `preview.py` | 非同步頁面渲染、過時請求淘汰、縮放與螢光筆 |
| `models.py` | 不可變搜尋選項、結果、頁面反白與抽取映射 |
| `i18n.py` | 英文與繁體中文文字目錄 |
| `resources.py` | 封裝後的應用程式圖像資源查找 |

搜尋核心不依賴 UI widget，因此可由測試或其他 Python 呼叫端獨立使用。

## 搜尋管線

1. `discover_documents` 依 `SearchOptions.search_scope` 選定的檔案類型，以穩定的相對路徑順序列舉；是否遞迴由 `SearchOptions.recursive` 控制。`SearchOptions.stem_glob` 可使用大小寫折疊後的 `fnmatchcase` glob 語法比對完整 `Path.stem`（只移除最後一個副檔名），留空不篩選。明確傳入 `paths` 時同樣會在讀取或轉換前篩選，因此進度與已搜尋檔案數只包含符合的檔案；此功能不受內文 Regex／大小寫設定影響，也不比對父資料夾名稱。
2. Word 文件先轉成使用者本機快取中的 PDF；Windows 優先使用 Microsoft Word，LibreOffice 為備援。`BackgroundWordPreparation` 在選定資料夾且搜尋類型包含 Word 時開始工作，主檔名、檔案類型或遞迴條件變更以 250 ms debounce 更新待轉清單。新條件取代尚未開始的舊排程，正在轉換的文件可完成並留下快取。專用執行緒以來源路徑、大小及修改時間識別共用 Future，搜尋沿用已完成或正在進行的結果，並優先處理搜尋正在等待的檔案。每批工作延遲啟動一個獨立 Word 程序，批次閒置時關閉；COM 的初始化、轉換及清理均在同一執行緒進行。快取皆有效時不啟動 Word；LibreOffice 維持逐檔子程序。快取識別亦包含轉換器；巨集與自動更新外部連結停用，來源以唯讀開啟。啟動時清除 30 天未使用的快取，並依最久未使用順序縮減至 500 MB。清除快取按鈕在搜尋或背景準備期間停用；清除後也會讓記憶體中的完成結果失效。
3. 每份產生的 PDF 獨立開啟；加密、損壞、空白、沒有文字層或無法轉換的檔案會成為不中斷搜尋的警告。
4. 每頁透過 PyMuPDF `rawdict` 抽取，並明確停用 `TEXT_PRESERVE_IMAGES`，避免搜尋文字時解碼圖片資料。
5. 依閱讀順序走訪文字區塊、行、span 與字元，每個可見字元都保存頁碼與精確 bounding box。
6. 行內空白會合併，一般換行與頁面邊界轉成空格；若行尾是連字號，會先移除再接續下一行。
7. 在完整正規化文件上搜尋。純文字會先跳脫；規則表達式採 Unicode `VERSION1`、可選完整大小寫折疊，以及單檔逾時。
8. 忽略零寬度命中；其他命中只映射實際涵蓋字元的方框。
9. 段落摘要以最近的中英文標點（`，。！？；：、,.!?;:`）為界；沒有標點時才使用有限字數與省略號。

正規化文字與 `CharacterRef` tuple 的長度永遠相同。人工加入的分隔空格帶有頁面參照但沒有方框，因此規則表達式可以跨頁，又不會產生不存在的反白區域。

## 漸進結果與並行處理

`SearchWorker` 在 Qt 全域 thread pool 中協調 `search_folder`；桌面搜尋將 PDF 抽取與文字匹配交由一個可重用的 spawn 子程序處理，避免 PyMuPDF 的 GIL 占用阻擋背景 Word 自動化。父程序透過 Pipe 接收逐筆命中、完整結果或個別檔案錯誤；同輪搜尋沿用同一子程序。取消時終止並回收子程序，桌面入口呼叫 `multiprocessing.freeze_support()` 以支援封裝程式。桌面介面傳入背景準備器的 `get_pdf`，依檔案順序搜尋；等待只發生在需要的文件尚未準備好時，不會重複轉換。背景轉檔不受搜尋速度影響，取消搜尋只取消該次等待，背景工作仍繼續；選取新資料夾或條件會替換待轉清單，關閉視窗才要求背景工作停止並清理。轉檔失敗在搜尋該檔案時轉為警告。UI 分別接收搜尋與背景轉檔狀態，可同時顯示兩階段檔名。

Word 轉檔在專用背景工作中逐份進行，PDF 搜尋則獨立運作。若搜尋比轉檔快，搜完一份後就會等待下一份 PDF，因此畫面可能看起來像轉檔與搜尋交替，但轉檔不會等待搜尋完成。再次搜尋會沿用仍有效的快取 PDF。

直接呼叫 `search_folder` 而未提供準備器時，仍使用該次搜尋專屬的轉檔執行緒與不設容量上限的路徑佇列，轉檔與搜尋獨立進行；結束或取消時清理該次工作。佇列只存路徑與錯誤，不存 PDF 內容。搜尋核心建立每個 `TextMatch` 後立即回呼，worker 透過 `match_found` 傳給主執行緒，逐筆更新結果並保留現有選取項目。

預覽渲染與搜尋彼此獨立。每次選取會建立 `PreviewRenderWorker`，使用自己的文件 handle 開啟 PDF，在 UI 執行緒之外渲染成 `QImage` 並畫上半透明反白。單調遞增的 request ID 會淘汰較舊的選取或縮放結果；只有轉換成 `QPixmap` 與更新 widget 在 UI 執行緒進行。

取消搜尋使用 thread-safe event；父程序在等待 IPC 與文件準備時持續檢查，必要時終止 PDF 搜尋子程序。Regex 另有逾時限制，防止災難性回溯。關閉視窗時會讓待處理預覽失效，並要求取消搜尋。

預設 `README.md` 使用繁體中文，因此 GitHub 與套件說明預設顯示繁體中文；英文維護於 `README.en.md`。兩份 README 都會納入原始碼套件。

## 介面與保存設定

主畫面使用頂端設定工具列與水平 splitter：

- 左側：上方是資料夾／主檔名篩選／樣式，下方是檔案與命中結果表；工具列三態按鈕可選擇 PDF、Word 或兩者。
- 右側：完整高度的 PDF 預覽、整份文件的上一頁／下一頁切換、符合寬度、符合頁面與縮放。

正式顯示名稱為 rgPDF；命令、Python 套件、快取路徑與設定識別名稱維持 `rgpdf`。選取命中項目時開啟其起始頁；預覽箭頭逐頁瀏覽文件（包含未命中頁），並在文件邊界停用。螢光標示仍對應目前選取的命中項目。「符合頁面」取可用預覽寬度／頁寬與高度／頁高的較小比例，不受手動縮放下限限制，確保大尺寸頁面也能完整顯示。兩種符合模式都會在窗格調整大小或換頁時重新計算；手動縮放會離開符合模式。

結果表停用標頭預設的最後一欄伸展，讓各欄的調整模式生效：檔案筆數依內容取寬，檔名使用剩餘寬度。

設定使用 `QSettings("rgpdf", "rgpdf")`：

| Key | 意義 |
| --- | --- |
| `appearance/language` | `system`、`zh_TW` 或 `en` |
| `appearance/theme` | `system`、`light` 或 `dark` |
| `appearance/highlight_color` | `#rrggbb` 螢光筆顏色 |
| `search/folder` | 上次選取的資料夾 |
| `search/stem_glob` | 主檔名 glob 篩選；留空不篩選 |
| `search/pattern` | 上次搜尋樣式 |
| `search/use_regex` | 規則表達式模式 |
| `search/case_sensitive` | 區分大小寫 |
| `search/recursive` | 包含子資料夾 |
| `search/scope` | `pdf`、`word` 或 `all` |
| `window/geometry` | 視窗位置與大小 |
| `window/main_splitter` | 左側／預覽比例 |
| `window/result_splitter` | 檔案／命中項目比例 |

主檔名篩選與搜尋樣式的說明圖示在各自輸入欄位左側垂直對齊，並共用 rich-text 說明彈窗，提供中英文語法說明與範例。圖示描邊共用 `SettingsButton.STROKE_WIDTH`，統一為 1 邏輯像素，包含 PDF 標誌外框。各窗格操作按鈕共用 34×34 px 尺寸、4 px 內距與 4 px 元件間距；圓形色票保留 28×28 px 尺寸。`SettingsToolBar` 在 Qt 的 polish、show 與 style-change 事件後重新套用共用間距與四邊各 4 px 留白。工具列高度維持 42 px（34 px 按鈕加上、下各 4 px），切換主題後也不改變。工具列的不對稱圖示以小幅垂直位移校正可見中心，與語言及配色圖示水平對齊。語言與主題按鈕各自循環三種模式；切換設定使用中性色的啟用樣式。螢光筆按鈕只有筆形圖示使用所選顏色，色彩面板提供常用色與原生 `QColorDialog`。

README 圖示由 `uv run python scripts/generate_toolbar_icons.py` 匯出：淺色圖片位於 `docs/toolbar/`，深色圖片位於 `docs/toolbar/dark/`。兩套圖片都使用共用按鈕繪製器，搭配主題的高對比文字色與不透明底板，以 2× 解析度輸出（68×68 px，顯示為 34×34 px）。README 的 `<picture>` 透過 `prefers-color-scheme: dark` 選擇深色圖片，並保留可讀的淺色備用圖，供忽略來源選擇的 viewer 使用。

## 測試與封裝

測試涵蓋純文字與 Regex、大小寫、跨頁映射、斷字合併、標點摘要、損壞／無文字 PDF、逐筆 callback、設定保存、主題切換、封裝 SVG 讀取與非同步預覽。測試亦涵蓋 Word 程序共用、背景預先轉檔、待轉條件調整、共用進行中的轉檔、快取失效、子程序重用、逐筆 IPC、繁重搜尋期間持續轉檔，以及取消清理。

```shell
uv sync
uv run pytest
uv build
```

`uv build` 會產生 sdist 與 wheel。SVG 程式圖示存放在 Python package 內，因此 editable 與正式建置都能透過 `importlib.resources` 取得。

應用程式的 SVG 圖示採等寬高輪廓與均衡留白，保留藍色折角文件及 `.*` 標誌；Windows 與 macOS 圖示產生器都沿用同一份 SVG。

## 發布流程

1. 在 `pyproject.toml` 與 `src/rgpdf/__init__.py` 設定相同版本。
2. 行為變更時同步更新中英文變更紀錄、README 與技術文件。
3. 本機執行測試並啟動 `uv run rgpdf` 供手動測試；執行檔只在遠端建置。
4. 提交並推送 `main`，建立並推送不可變的 `vX.Y.Z` 標籤。
5. tag 推送會觸發 `.github/workflows/publish-pypi.yml`，遠端測試與建置 Windows／macOS 發布檔、建立 GitHub Release，再透過 Trusted Publishing 發布至 PyPI。
6. 發布工作流程成功後，將 `latest` 原始碼標籤移至相同 commit。

安裝文件必須使用 PyPI 的最新發布版本或會移動的 `latest` 原始碼標籤，不得寫死版本標籤；不可變版本標籤則保留給可重現的原始碼 checkout 與發布歷程。PyPI 專案必須信任儲存庫 `codemee/rgpdf`、工作流程 `publish-pypi.yml` 與 environment `pypi`，GitHub 不保存長效上傳 token。
