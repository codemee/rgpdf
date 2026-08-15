# rgpdf

繁體中文 · [English](README.md)

rgpdf 是一套跨平台桌面工具，可使用純文字或規則表達式搜尋具有文字層的 PDF。每筆命中會在找到時立即顯示，並可在非同步頁面預覽中查看精確且可自訂顏色的螢光筆標示。

## 功能

- 搜尋資料夾內的多份 PDF，並可選擇是否包含子資料夾。
- 支援純文字、規則表達式及區分大小寫。
- 支援跨行、跨頁匹配與行尾英文斷字合併。
- 每找到一筆結果就立即顯示，搜尋期間介面仍可操作。
- 檔案、命中段落與 PDF 頁面預覽三個連動區域。
- 逐字元反白座標與可自訂的螢光筆顏色。
- 繁體中文／英文介面，以及系統／淺色／深色主題。
- 保存搜尋與外觀偏好。

rgpdf 只搜尋 PDF 已有的文字層，不執行 OCR，也不修改來源檔案。

## 安裝最新版本

先安裝 [uv](https://docs.astral.sh/uv/)，再安裝會移動到最新版本的 `latest` 標籤：

```shell
uv tool install --force --refresh "git+https://github.com/codemee/rgpdf.git@latest"
```

執行程式：

```shell
rgpdf
```

日後更新時，再次執行相同的 `uv tool install --force --refresh ...@latest` 指令即可。支援 Windows 與 macOS，所需 Python 環境由 uv 管理。

## 開發

```shell
git clone https://github.com/codemee/rgpdf.git
cd rgpdf
uv sync
uv run pytest
uv run rgpdf
```

架構、匹配語意、並行處理與發布方式請參閱[技術細節](docs/TECHNICAL.zh-TW.md)，版本歷程請參閱[變更紀錄](CHANGELOG.zh-TW.md)。

## 發布版本

不可變的發布版本使用 `v0.0.1` 之類的版本標籤；可移動的 `latest` Git 標籤永遠指向最新發布版本，也是文件中的標準安裝來源。

