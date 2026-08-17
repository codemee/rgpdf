# 發布與授權檢查清單

rgpdf 以 `AGPL-3.0-only` 授權，並使用 AGPLv3 的 PyMuPDF/MuPDF 與
LGPLv3 的 PySide6/Qt。每次散布執行檔時都要完成以下事項。

## 建置

1. 從不可變的 `vX.Y.Z` tag 建置，不可直接從會移動的 `latest` 建置。
2. 使用 `uv sync --frozen`，確保相依版本與 `uv.lock` 完全一致。
3. 保存產生執行檔所使用的 spec、工作流程、資源與所有建置腳本。
4. 在乾淨的 Windows 環境確認「關於 rgpdf」顯示正確版本、授權與原始碼連結。

推送與專案版本相同的 `vX.Y.Z` tag 後，`.github/workflows/publish-pypi.yml` 會自動完成版本驗證、測試、Windows x86_64 與 macOS arm64 建置、第三方對應來源封裝、GitHub Release 及 PyPI 發布。這個小型專案不使用 Apple Developer ID；macOS App 保留 PyInstaller 的 ad-hoc 簽章且不做公證，因此其他使用者首次開啟時可能需要在 Finder 中按右鍵選擇「打開」。

## GitHub Release 必備項目

同一個 Release 應提供：

- `rgpdf-X.Y.Z-windows-x86_64.exe`
- `rgpdf-X.Y.Z-macos-arm64.dmg`
- `rgpdf-X.Y.Z-source.tar.gz`：該 tag 的完整 rgpdf 對應原始碼與建置腳本
- `rgpdf-X.Y.Z-third-party-sources.tar.gz`：建置所用 PyMuPDF/MuPDF、
  PySide6/Shiboken6/Qt 的確切來源與授權文件
- `LICENSE`
- `THIRD-PARTY-NOTICES.md`

第三方來源必須由本專案控制並持續提供；不要只放上游網站連結。
Release 說明應清楚標示執行檔及其對應原始碼的下載位置。

`third-party-sources.toml` 固定每個上游封存檔的 URL 與 SHA-256。更新 PyMuPDF 或 PySide6 後也必須更新這份 manifest；若其中版本與 `uv.lock` 不一致，發布工作流程會停止。

## LGPL 注意事項

PySide6/Qt 採 LGPLv3 選項。使用者必須能修改、替換或重新連結 Qt 程式庫，
並能執行修改後的版本。因此應提供完整建置說明、Qt 對應來源和必要安裝資訊，
且不得以額外條款禁止反向工程或修改 Qt 元件。

真正的單檔封裝會增加替換 Qt DLL 的難度。正式採用單檔格式前，應驗證公開的
建置材料足以讓接收者以修改後的 Qt/PySide6 重建並執行 rgpdf；若無法確保，
應改發可替換 DLL 的資料夾版，或取得 Qt 商業授權。

## 保存期限

不要刪除仍在散布之執行檔的對應來源。即使日後發布新版，舊版 binary 所對應的
tag、來源封存檔和第三方來源仍應保持可取得。
