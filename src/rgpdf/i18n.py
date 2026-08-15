from __future__ import annotations


TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh_TW": {
        "app_title": "rgpdf — PDF 搜尋",
        "folder": "PDF 資料夾",
        "browse": "瀏覽…",
        "pattern": "搜尋樣式",
        "pattern_hint": "輸入文字或正規表示式",
        "pattern_tooltip": (
            "<b>搜尋樣式</b><br>"
            "停用規則表達式時，輸入內容會視為完整的純文字。<br>"
            "啟用時可使用例如：<br>"
            "• <code>範例\\s*\\d+</code>：『範例』、可選空白與一串數字<br>"
            "• <code>錯誤|警告</code>：符合其中任一文字<br>"
            "• <code>\\b[A-Z]{{2}}\\d{{4}}\\b</code>：兩個大寫字母加四位數字<br>"
            "語法參考：https://github.com/mrabarnett/mrab-regex#readme"
        ),
        "plain": "純文字",
        "regex": "規則表達式",
        "case": "區分大小寫",
        "recursive": "包含子資料夾",
        "highlight_settings": "螢光筆顏色",
        "common_colors": "常用顏色",
        "custom_color": "自訂顏色…",
        "choose_highlight_color": "選擇螢光筆顏色",
        "settings": "設定",
        "enabled": "啟用",
        "disabled": "停用",
        "search": "搜尋",
        "cancel": "取消",
        "files": "檔案",
        "matches": "命中項目",
        "filename": "檔名",
        "count": "筆數",
        "page_number": "頁碼",
        "paragraph": "段落",
        "preview": "頁面預覽",
        "ready": "選取資料夾並輸入搜尋樣式",
        "searching": "正在搜尋 {current}/{total}：{name}",
        "done": "完成：搜尋 {scanned} 份 PDF，{files} 份有結果，共 {matches} 筆命中",
        "cancelled": "搜尋已取消：已處理 {scanned} 份 PDF",
        "no_results": "找不到符合項目",
        "choose_folder": "選取 PDF 資料夾",
        "invalid": "無法搜尋",
        "warnings": "部分檔案無法搜尋",
        "warning_body": "略過 {count} 份檔案：\n\n{details}",
        "language": "語言",
        "theme": "主題",
        "system": "跟隨系統",
        "light": "淺色",
        "dark": "深色",
        "traditional_chinese": "繁體中文",
        "english": "English",
        "page": "第 {page} 頁，共 {total} 頁",
        "previous_page": "上一個命中頁",
        "next_page": "下一個命中頁",
        "zoom_out": "縮小",
        "zoom_in": "放大",
        "fit": "符合寬度",
        "page_single": "第 {start} 頁",
        "page_range": "第 {start}–{end} 頁",
        "match_count": "{count} 筆",
    },
    "en": {
        "app_title": "rgpdf — PDF Search",
        "folder": "PDF folder",
        "browse": "Browse…",
        "pattern": "Search pattern",
        "pattern_hint": "Enter text or a regular expression",
        "pattern_tooltip": (
            "<b>Search pattern</b><br>"
            "With Regular Expression off, the input is matched as literal text.<br>"
            "With it on, examples include:<br>"
            "• <code>example\\s*\\d+</code>: ‘example’, optional whitespace, then digits<br>"
            "• <code>error|warning</code>: either word<br>"
            "• <code>\\b[A-Z]{{2}}\\d{{4}}\\b</code>: two uppercase letters and four digits<br>"
            "Syntax reference: https://github.com/mrabarnett/mrab-regex#readme"
        ),
        "plain": "Plain text",
        "regex": "Regular Expression",
        "case": "Case sensitive",
        "recursive": "Include subfolders",
        "highlight_settings": "Highlight color",
        "common_colors": "Common colors",
        "custom_color": "Custom color…",
        "choose_highlight_color": "Choose highlight color",
        "settings": "Settings",
        "enabled": "On",
        "disabled": "Off",
        "search": "Search",
        "cancel": "Cancel",
        "files": "Files",
        "matches": "Matches",
        "filename": "File name",
        "count": "Count",
        "page_number": "Page",
        "paragraph": "Paragraph",
        "preview": "Page preview",
        "ready": "Choose a folder and enter a search pattern",
        "searching": "Searching {current}/{total}: {name}",
        "done": "Done: searched {scanned} PDFs, {files} files matched, {matches} matches",
        "cancelled": "Search cancelled after {scanned} PDFs",
        "no_results": "No matches found",
        "choose_folder": "Choose PDF folder",
        "invalid": "Cannot search",
        "warnings": "Some files could not be searched",
        "warning_body": "Skipped {count} files:\n\n{details}",
        "language": "Language",
        "theme": "Theme",
        "system": "Follow system",
        "light": "Light",
        "dark": "Dark",
        "traditional_chinese": "繁體中文",
        "english": "English",
        "page": "Page {page} of {total}",
        "previous_page": "Previous matched page",
        "next_page": "Next matched page",
        "zoom_out": "Zoom out",
        "zoom_in": "Zoom in",
        "fit": "Fit width",
        "page_single": "Page {start}",
        "page_range": "Pages {start}–{end}",
        "match_count": "{count} matches",
    },
}


def translate(language: str, key: str, **values: object) -> str:
    catalog = TRANSLATIONS.get(language, TRANSLATIONS["en"])
    return catalog.get(key, TRANSLATIONS["en"].get(key, key)).format(**values)
