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

### Windows 免安裝版

從 [最新 GitHub Release](https://github.com/codemee/rgpdf/releases/latest)下載有版本編號的 `rgpdf-*-windows-x86_64.exe` 與對應 `.sha256` 檔。執行檔目前未簽章，因此 Windows SmartScreen 可能顯示未知發布者警告；選擇執行前，請先確認 SHA-256 與發布頁提供的值相同。

免安裝版不需要 Python 或 uv。

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

建置不需使用者安裝 Python 或 uv 的 Windows 單一執行檔（只有建置電腦需要）：

```powershell
uv sync --frozen
./scripts/build-windows.ps1 -Python .venv/Scripts/python.exe
```

建置結果為 `dist/rgpdf.exe`。GitHub Actions 也會將執行檔、`LICENSE` 與第三方授權聲明發布為 `rgpdf-windows-x86_64` workflow artifact。正式公開散布前，仍須提供[發布授權檢查清單](docs/RELEASING.zh-TW.md)所列的對應來源材料。

在 macOS 建置可直接開啟、無需另裝 Python 的 App：

```shell
uv sync --frozen
./scripts/build-macos.sh
open dist/rgpdf.app
```

建置結果為 `dist/rgpdf.app`，架構與建置用的 Mac 相同（Apple Silicon 為 `arm64`、Intel Mac 為 `x86_64`）。本專案不使用 Apple Developer ID，App 只有 ad-hoc 簽章且不做公證；其他使用者首次開啟時可能需要在 Finder 中按右鍵選擇「打開」。

架構、匹配語意、並行處理與發布方式請參閱[技術細節](docs/TECHNICAL.zh-TW.md)，版本歷程請參閱[變更紀錄](CHANGELOG.zh-TW.md)。

## 發布版本

不可變的發布版本使用 `v0.0.3` 之類的版本標籤；可移動的 `latest` Git 標籤永遠指向最新的原始碼發布版本。PyPI 則提供標準的套件發布版本。

發布流程由 GitHub Actions 自動執行。確認 `pyproject.toml` 與 `src/rgpdf/__init__.py` 的版本一致並推送對應 tag：

```shell
git tag v0.0.5
git push origin v0.0.5
```

workflow 會平行測試並建置 Windows x86_64 與 macOS arm64，下載並驗證鎖定版本的第三方對應原始碼，建立同一個 GitHub Release、附加 SHA-256 校驗檔，最後透過 Trusted Publishing 發布至 PyPI。若任一測試、建置或來源驗證失敗，就不會建立 Release 或發布 PyPI。

## 授權

rgpdf 依 [GNU Affero General Public License version 3](LICENSE) 授權。你可以依該授權條款使用、研究、修改及重新散布本程式；散布執行檔時，必須同時提供該版本的完整對應原始碼。

本程式依 AGPLv3 使用 PyMuPDF/MuPDF，並依 LGPLv3 使用 PySide6/Qt。詳見[第三方授權聲明](THIRD-PARTY-NOTICES.md)與[發布授權檢查清單](docs/RELEASING.zh-TW.md)。
