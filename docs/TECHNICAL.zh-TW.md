# rgPDF 技術細節

繁體中文 · [English](TECHNICAL.md)

## 技術與模組邊界

rgPDF 支援 Python 3.12–3.13，並由 uv 管理。PySide6 提供桌面介面，PyMuPDF 負責 PDF 文字抽取與頁面渲染，第三方 `regex` 套件則提供 Unicode 規則表達式與單檔逾時限制。Windows 建置使用 pywin32，要求既有的 Microsoft Word 執行固定格式匯出。

| 模組 | 職責 |
| --- | --- |
| `app.py` | QApplication 生命週期、調色盤、扁平樣式與啟動流程 |
| `buttons.py` | 共用且配合主題的向量操作按鈕、中英文 tooltip 與無障礙名稱 |
| `progress.py` | 進度百分比依填滿區裁切，以不同前景色維持對比 |
| `main_window.py` | 搜尋控制、設定工具列、漸進式結果模型與畫面連動 |
| `search.py` | 檔案探索、轉換分派、PDF 抽取、正規化、比對及座標映射 |
| `layout_text.py` | 依版面接合相鄰行，保留字元座標與儲存格邊界 |
| `word_screening.py` | 保守 DOCX 文字初篩；不確定時交由 PDF 搜尋 |
| `word_conversion.py` | Word／LibreOffice 轉換器選擇與本機 PDF 快取 |
| `word_export.py` | 背景 Word 清單與沿用快取的批次 PDF 匯出 |
| `export_dialog.py` | 匯出勾選、輸出目錄與同名檔案驗證 |
| `system_menu.py` | Windows 原生系統功能表整合 |
| `worker.py` | 背景搜尋工作與跨執行緒 Qt signal |
| `pdf_search_process.py` | 可重用的 PDF 搜尋子程序、逐筆命中 IPC 與取消清理 |
| `pdf_passwords.py` | 共用 PDF 密碼驗證與以來源指紋識別的工作階段記憶體密碼 |
| `preview.py` | 非同步頁面渲染、過時請求淘汰、縮放與螢光筆 |
| `preview_text.py` | 逐字座標文字層、滑鼠選取、鍵盤／選單複製與選取標示 |
| `models.py` | 不可變搜尋選項、結果、頁面反白與抽取映射 |
| `i18n.py` | 英文與繁體中文文字目錄 |
| `resources.py` | 封裝後的應用程式圖像資源查找 |

搜尋核心不依賴 UI widget，因此可由測試或其他 Python 呼叫端獨立使用。

## Word PDF 匯出

匯出圖示結合 14×14 px Word 標誌與 1 px 向外箭頭，整體維持共用的 20×20 px 範圍；箭頭隨配色變化，停用時降低標誌透明度。`word_export.py` 提供背景清單與快取匯出；`export_dialog.py` 提供檔案勾選、輸出目錄及同名檢查。防抖掃描依子資料夾與主檔名 glob 設定列出 Word 檔，不受搜尋樣式與搜尋類型限制，排除 `~$` 鎖定檔，並拒絕過時的 request ID。目錄監視器更新目前根目錄與清單中 Word 檔所在目錄的變化。對話框以相對路徑提供勾選清單、輸出資料夾及預設關閉的覆寫選項，拒絕空白選取、無效輸出目錄及不區分大小寫的重複 PDF 檔名。輸出平放於指定目錄，保留原主檔名。

`WordExportWorker` 與搜尋及清除快取互斥。先呼叫 `cached_word_pdf`，因此即使未安裝轉檔程式，也能沿用任一渲染器的有效快取；缺少快取才透過共用指紋快取 API 與延遲啟動的 `word_conversion_session` 轉檔，不做內容初篩。先在輸出目錄暫存完整 PDF，再以獨占建立方式複製；明確選擇覆寫時才取代目標。獨占建立可避免檢查後才出現的同名檔遭覆寫，也不依賴硬連結支援。複製失敗會清除未完成的輸出，收集個別錯誤並繼續其他檔案。狀態列顯示進度，可取消並保留已完成的匯出與快取；關閉視窗會取消後續作業。最後輸出資料夾儲存於 `export/folder`。

## 搜尋管線

1. `discover_documents` 依 `SearchOptions.search_scope` 選定的檔案類型，以穩定的相對路徑順序列舉；是否遞迴由 `SearchOptions.recursive` 控制。`SearchOptions.stem_glob` 可使用大小寫折疊後的 `fnmatchcase` glob 語法比對完整 `Path.stem`（只移除最後一個副檔名），留空不篩選。明確傳入 `paths` 時同樣會在讀取或轉換前篩選，因此進度與已搜尋檔案數只包含符合的檔案；此功能不受內文 Regex／大小寫設定影響，也不比對父資料夾名稱。
2. Word 文件先初篩，再將候選文件排入 PDF 轉換佇列。`word_may_match` 以串流方式解析 DOCX 中的 WordprocessingML 文字，跨 run 檢查純文字樣式，第一個可能命中即返回；不建立頁碼或正式命中。初篩不區分大小寫，放寬空白及連字號，以正規化後的連續詞句比對，不以零散字元是否存在判定命中；只讀取正文、頁首頁尾、註腳、章末註及圖表等內容，不搜尋樣式定義。包含運算子的 Regex、舊式 `.doc`、動態欄位、嵌入物件或解析失敗直接轉 PDF；啟用 Regex 但樣式沒有運算子時仍使用文字初篩。圖片、編號及未使用樣式不會讓整份文件直接通過初篩，圖形文字亦納入擷取。有效 PDF 快取優先，略過文字初篩。Windows 優先使用 Microsoft Word，LibreOffice 為備援；每批候選共用延遲啟動的 Word 程序，COM 初始化、匯出及清理均在轉檔執行緒進行。巨集及自動更新連結停用，來源唯讀。快取以轉換器、來源路徑、大小及修改時間識別；啟動時清理 30 天未使用項目並依 LRU 縮減至 500 MB，搜尋或批次匯出 PDF 期間停用手動清除。
3. 每份 PDF 獨立開啟。需要密碼時，`unlock_pdf` 透過可選的 `password_requested(path, incorrect)` 回呼取得密碼，使用 `Document.authenticate()` 驗證；錯誤可重試，略過則為逐檔警告。驗證通過才呼叫 `password_accepted`，之後正常擷取與匹配。損壞、空白、無文字層或無法轉換的文件仍為不中斷搜尋的警告。
4. 每頁透過 PyMuPDF `rawdict` 抽取，並明確停用 `TEXT_PRESERVE_IMAGES`，避免搜尋文字時解碼圖片資料。
5. 依閱讀順序走訪文字區塊、行、span 與字元，每個可見字元都保存頁碼與精確 bounding box。
6. 行內空白會合併，一般換行與頁面邊界轉成空格；若行尾是連字號，會先移除再接續下一行。 可選的 `SearchOptions.ignore_line_wraps` 預設關閉；啟用時，`layout_text.py` 以 RAWDICT 區塊及方向、行距、左右重疊範圍與偵測到的儲存格判斷同頁相鄰行是否為排版換行。中文邊界省略人工空格；英文保留一個空格，ASCII 字母間的行尾連字號移除。真實行內／行邊空格不移除。不同區塊、欄位或儲存格使用硬分隔，跨頁維持空格。表格分析只在有向量路徑時執行，偵測失敗則停用該頁接合。此為保守版面推斷，無法保證辨識所有無框線表格或被合併的段落。
7. 在完整正規化文件上搜尋。純文字會先跳脫；規則表達式採 Unicode `VERSION1`、可選完整大小寫折疊，以及單檔逾時。
8. 忽略零寬度命中；其他命中只映射實際涵蓋字元的方框。
9. 命中摘要以最近的中英文標點（`，。！？；：、,.!?;:`）及段落／儲存格換行分隔為邊界，且無論有無標點，前後文都受半徑限制。摘要中的換行與空白合併成單一空格，總長度最多 160 字元；過長的命中文字亦縮略，但 `matched_text`、實際命中座標及 PDF 標示完整保留。

正規化文字與 `CharacterRef` tuple 的長度永遠相同。人工加入的分隔空格帶有頁面參照但沒有方框，因此規則表達式可以跨頁，又不會產生不存在的反白區域。

## 漸進結果與並行處理

`SearchWorker` 在 Qt 全域 thread pool 中協調 `search_folder`。管線有三個可同時進行的階段：初篩執行緒將候選路徑送入不設容量上限的佇列；轉檔執行緒依序匯出 PDF；搜尋協調者消費已就緒 PDF，透過可重用的 spawn 子程序抽取文字並搜尋。既有 PDF 與有效快取不必等待尚未完成的 Word 轉換。佇列只保存路徑與錯誤，不保存 PDF 內容。

父程序透過 Pipe 接收逐筆命中、完整結果與個別檔案錯誤；同輪搜尋沿用一個子程序，以免 PDF 搜尋的 GIL 占用阻擋 Word 自動化。桌面入口使用 `multiprocessing.freeze_support()` 支援封裝執行。只有 PDF 搜尋產生的 `TextMatch` 才送至結果窗格，因此頁碼、筆數及矩形均來自同一份 PDF，不需比對 DOCX 與 PDF 的文字位移。候選初篩可能是假陽性，PDF 無命中時不顯示該文件。就緒文件可先回報，不必等待較早文件；單份 PDF 的命中仍依文字順序逐筆回報。UI 顯示初篩進度、累計候選數、搜尋及轉檔中的檔名。

選定資料夾與變更篩選條件只影響下次搜尋，不再預先轉換整個資料夾。取消或關閉視窗會停止初篩與未開始的轉換、終止 PDF 搜尋子程序，並在正在執行的 Word 呼叫返回後清理轉檔執行緒及 COM。正式搜尋失敗仍回報逐檔警告，不阻止後續文件。

加密 PDF 的子程序驗證以 Pipe 訊息往返：子程序送出需要密碼／錯誤狀態，父程序提供輸入，子程序成功後送出驗證確認，再串流命中。`SearchWorker` 發出 `PdfPasswordRequest`，UI 以非阻塞、密碼遮罩的 `QInputDialog` 回應；等待每 50 ms 檢查取消，關閉或取消時拒絕提示並終止子程序，不使用背景執行緒操作 widget。成功密碼存入視窗持有的 `PdfPasswords`，以絕對路徑、大小與修改時間識別，供重搜與每次預覽渲染重新驗證；預覽工作完成後清除自身的暫時密碼參照。密碼不放進 `SearchOptions`／結果模型、QSettings、警告或磁碟快取，不輸出解密副本。關閉視窗清除密碼，並拒收延後抵達的驗證結果。

預覽渲染與搜尋彼此獨立。每次選取會建立 `PreviewRenderWorker`，使用自己的文件 handle 開啟 PDF，在 UI 執行緒之外渲染成 `QImage` 並畫上半透明反白。單調遞增的 request ID 會淘汰較舊的選取或縮放結果；只有轉換成 `QPixmap` 與更新 widget 在 UI 執行緒進行。

預覽渲染工作在同一個已驗證的文件 handle 內抽取目前頁面的 `rawdict`（停用影像內容），建立不可變 `PageText`／`PageGlyph`／`PageLine`。文字保留行與區塊換行；逐字矩形透過 `page.rotation_matrix` 轉成顯示座標，命中標示亦套用相同轉換。`SelectablePageLabel` 依縮放與圖片原點將滑鼠座標還原，先找行再找字元，以方向判定選取端點。工具列使用單一「選取並複製文字」按鈕，圖示為文字橫線搭配選取游標。拖曳時僅畫半透明選取層，放開滑鼠後才自動複製；整頁全選亦自動複製，不修改 PDF。支援正反向選取、Esc 清除、Ctrl+C／⌘C 與右鍵選單。換頁、換檔與重繪會清除選取並停用舊文字層；過時 request ID 不得恢復文字層。Windows 剪貼簿暫時占用時以短間隔有限次重試，關閉或清除文件取消尚待複製的內容。

預覽工具列以分隔線分成翻頁、複製及縮放三組。整頁影像複製透過 `QBuffer` 在記憶體中將完整渲染 pixmap 編碼為 PNG，以 `QMimeData` 同時提供 `image/png` 與原生圖片資料。保留目前預覽解析度與命中標示，不包含額外繪製的文字選取底色。獨立的渲染就緒狀態避免換頁或重繪期間複製到舊頁面，不依賴文字層。Windows 透過剪貼簿擁有權判定是否需要有限次定時重試；清除文件會取消待處理的圖片複製。

取消搜尋使用 thread-safe event；父程序在等待 IPC 與文件準備時持續檢查，必要時終止 PDF 搜尋子程序。Regex 另有逾時限制，防止災難性回溯。關閉視窗時會讓待處理預覽失效，並要求取消搜尋。

預設 `README.md` 使用繁體中文，因此 GitHub 與套件說明預設顯示繁體中文；英文維護於 `README.en.md`。兩份 README 都會納入原始碼套件。

## 介面與保存設定

主畫面使用頂端設定工具列與水平 splitter：

- 左側：上方「搜尋標的」群組包含資料夾／主檔名篩選／樣式，下方是檔案與命中結果表；工具列三態按鈕可選擇 PDF、Word 或兩者。
- 右側：完整高度的 PDF 預覽、整份文件的上一頁／下一頁切換、符合寬度、符合頁面與縮放。

正式顯示名稱為 rgPDF；命令、Python 套件、快取路徑與設定識別名稱維持 `rgpdf`。選取命中項目時開啟其起始頁；預覽箭頭逐頁瀏覽文件（包含未命中頁），並在文件邊界停用。螢光標示仍對應目前選取的命中項目。「符合頁面」取可用預覽寬度／頁寬與高度／頁高的較小比例，不受手動縮放下限限制，確保大尺寸頁面也能完整顯示。兩種符合模式都會在窗格調整大小或換頁時重新計算；手動縮放會離開符合模式。

結果表停用標頭預設的最後一欄伸展，讓各欄的調整模式生效：檔案筆數依內容取寬，檔名使用剩餘寬度。

工具列以可伸展的 spacer 將「語言、配色」固定在右側，前方設有分隔線，搜尋工具維持左側；工具列高度與間距不變。「關於」共用 QAction：Windows 透過 `system_menu.py` 以符合指標寬度的 Win32 宣告，在原生系統功能表的「關閉」前加入本地化項目；僅攔截自訂 WM_SYSCOMMAND ID，排入 Qt 事件迴圈觸發對話框。重複顯示或切換語言會更新原項目，避免重複加入；其他系統命令仍交由 Qt 處理。其他平台使用 AboutRole 功能表動作，macOS 會將其放入原生應用程式功能表。搜尋狀態 QLabel 與 SearchProgressBar 放入 QMainWindow 的 QStatusBar，橫跨整個視窗；狀態文字與進度條以 3:2 分配空間，進度條最小寬度為 240 px，長文字不強制撐大視窗並可用 tooltip 查看。MainWindow 接受本機 URL 的 CopyAction 拖放：資料夾直接作為標的，檔案使用所在資料夾；多項拖放取第一個有效本機項目，忽略遠端 URL、無效路徑及只允許移動的事件。選定資料夾會沿用瀏覽功能的設定保存，不修改來源、不自動搜尋；搜尋、批次匯出 PDF 期間與關閉後拒絕拖放。輸入欄位停用原生 URL 拖放，避免將檔案路徑插入搜尋樣式。

設定使用 `QSettings("rgpdf", "rgpdf")`：

| Key | 意義 |
| --- | --- |
| `appearance/language` | `system`、`zh_TW` 或 `en` |
| `appearance/theme` | `system`、`light` 或 `dark` |
| `appearance/highlight_color` | `#rrggbb` 螢光筆顏色 |
| `search/folder` | 上次選取的資料夾 |
| `export/folder` | 上次 Word PDF 匯出資料夾 |
| `search/stem_glob` | 主檔名 glob 篩選；留空不篩選 |
| `search/pattern` | 上次搜尋樣式 |
| `search/use_regex` | 規則表達式模式 |
| `search/ignore_line_wraps` | 忽略排版換行；預設關閉 |
| `search/case_sensitive` | 區分大小寫 |
| `search/recursive` | 包含子資料夾 |
| `search/scope` | `pdf`、`word` 或 `all` |
| `window/geometry` | 視窗位置與大小 |
| `window/main_splitter` | 左側／預覽比例 |
| `window/result_splitter` | 檔案／命中項目比例 |

主檔名篩選與搜尋樣式的說明圖示在各自輸入欄位左側垂直對齊，並共用 rich-text 說明彈窗，提供中英文語法說明與範例。PDF 標誌以 `QSvgRenderer` 繪製隨套件附帶的 Adobe Acrobat SVG，PDF 與 Word 單獨模式共用 16×16 px 尺寸，組合模式兩者皆為 14×14 px，將 PDF 放在左上、W 放在右下並局部交疊，保留標誌主體可辨識性；兩平台封裝均包含此 SVG，來源記錄於第三方聲明。圖示描邊共用 `SettingsButton.STROKE_WIDTH`，統一為 1 邏輯像素；品牌標誌保留原始向量圖形。各窗格操作按鈕共用 34×34 px 尺寸、4 px 內距與 4 px 元件間距；圓形色票保留 28×28 px 尺寸。`SettingsToolBar` 在 Qt 的 polish、show 與 style-change 事件後重新套用共用間距與四邊各 4 px 留白。工具列高度維持 42 px（34 px 按鈕加上、下各 4 px），切換主題後也不改變。工具列的不對稱圖示以小幅垂直位移校正可見中心，與語言及配色圖示水平對齊。語言與主題按鈕各自循環三種模式；狀態按鈕啟用時沿用滑鼠移入的 `palette(midlight)` 底色，不繪製外框；背景共用 `SettingsButton.CORNER_RADIUS` 的 8 px 圓角。深色模式採初號機風格的深紫底色、螢光綠啟用圖示、綠底深色選取文字，以及橘色焦點／連結；淺色模式保留中性的啟用樣式。螢光筆顏色按鈕以置中的 16×16 px 單一色塊顯示所選顏色，瀏覽與遞迴資料夾圖示使用無填色的主題單色線條，前後資料夾共用 14×10 px 輪廓、錯位 6×6 px，前方以裁切遮住後方線條；色彩面板提供常用色與原生 `QColorDialog`。

README 圖示由 `uv run python scripts/generate_toolbar_icons.py` 匯出：淺色圖片位於 `docs/toolbar/`，深色圖片位於 `docs/toolbar/dark/`。兩套圖片都使用共用按鈕繪製器，搭配主題的高對比文字色與不透明底板，以 2× 解析度輸出（68×68 px，顯示為 34×34 px）。README 的 `<picture>` 透過 `prefers-color-scheme: dark` 選擇深色圖片，並保留可讀的淺色備用圖，供忽略來源選擇的 viewer 使用。

`SearchProgressBar` 保留原進度條背景與填滿區樣式，自繪百分比文字：底層採 `Text` 色，填滿區裁切後採 `HighlightedText` 色，使深色主題的螢光綠進度上使用深色文字、未填滿區使用淺色文字；也支援由右向左及反向進度。

## 測試與封裝

測試涵蓋純文字與 Regex、大小寫、跨頁映射、斷字合併、摘要、損壞與無文字 PDF、逐筆結果、設定、主題與預覽；另驗證 DOCX 初篩、特殊內容備援、快取略過初篩、候選與正式結果分離、轉檔期間持續初篩、已就緒 PDF 優先、子程序重用及取消清理。另涵蓋 AES 加密 PDF 的開啟／擁有者密碼、錯密碼重試、逐檔略過、免開啟密碼、預覽換頁、工作階段密碼清除，以及等待密碼時取消或關閉。

測試亦涵蓋旋轉與加密頁面的文字選取、自動複製與剪貼簿重試、整頁 PNG MIME 資料、系統功能表事件與語言切換、Word 匯出的快取重用與建立、檔名衝突、略過／覆寫、取消、檔案篩選、舊掃描結果拒絕及主視窗匯出流程。

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
