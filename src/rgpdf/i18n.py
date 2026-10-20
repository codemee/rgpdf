# Copyright (C) 2026 meebox
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations


TRANSLATIONS: dict[str, dict[str, str]] = {
    "zh_TW": {
        "app_title": "rgPDF {version} — 文件搜尋",
        "folder": "文件資料夾",
        "stem_filter": "主檔名篩選",
        "stem_filter_hint": "例如 ch0*；留空搜尋所有主檔名",
        "stem_filter_help_title": "主檔名篩選說明",
        "stem_filter_help_content": (
            "<b>主檔名篩選（Glob）</b><br>"
            "留空時不篩選。只比對不含最後一個副檔名的完整主檔名，不比對資料夾名稱，且不區分大小寫。<br>"
            "• <code>*</code>：任意長度字串（可為空）<br>"
            "• <code>?</code>：單一字元<br>"
            "• <code>[abc]</code>：集合中的任一字元<br>"
            "• <code>[0-9]</code>：範圍中的任一字元<br>"
            "• <code>[!abc]</code>：集合以外的單一字元<br>"
            "<b>範例</b><br>"
            "• <code>ch0*</code>：符合 ch01、ch02，不符合 ch1、ch2<br>"
            "• <code>ch0?</code>：符合 ch01，不符合 ch001<br>"
            "• <code>ch0[1-3]</code>：符合 ch01、ch02、ch03<br>"
            "• <code>ch01</code>：只符合完整主檔名 ch01（例如 ch01.pdf、ch01.docx）<br>"
            "此欄位使用 Glob 語法，不受內文搜尋的規則表達式與區分大小寫設定影響。"
        ),
        "stem_filter_help": "只比對不含副檔名的主檔名，不區分大小寫。支援 *（任意字串）、?（單一字元）、[abc]、[0-9]、[!abc]。例如 ch0* 比對 ch01、ch02，不比對 ch1、ch2。留空不篩選。",
        "file_types": "搜尋檔案",
        "scope_pdf": "僅 PDF",
        "scope_word": "僅 Word（DOC、DOCX）",
        "scope_all": "PDF 與 Word",
        "browse": "瀏覽…",
        "pattern": "搜尋樣式",
        "pattern_hint": "輸入文字或正規表示式",
        "pattern_help": "搜尋樣式說明",
        "pattern_help_content": (
            "<b>搜尋樣式</b><br>"
            "停用規則表達式時，輸入內容會視為完整的純文字。<br>"
            "啟用時可使用例如：<br>"
            "• <code>範例\\s*\\d+</code>：『範例』、可選空白與一串數字<br>"
            "• <code>錯誤|警告</code>：符合其中任一文字<br>"
            "• <code>\\b[A-Z]{{2}}\\d{{4}}\\b</code>：兩個大寫字母加四位數字<br>"
            "語法參考：<a href=\"https://github.com/mrabarnett/mrab-regex#readme\">"
            "regex 語法文件</a>"
        ),
        "plain": "純文字",
        "regex": "規則表達式",
        "case": "區分大小寫",
        "recursive": "包含子資料夾",
        "highlight_settings": "螢光筆顏色",
        "common_colors": "常用顏色",
        "custom_color": "自訂顏色…",
        "choose_highlight_color": "選擇螢光筆顏色",
        "clear_word_cache": "清除 Word 快取",
        "clear_cache_confirm": "要刪除所有 Word 轉換產生的快取 PDF 嗎？這不會刪除原始文件。",
        "cache_cleared_body": "已刪除 {count} 個快取檔案，釋放 {size} MB。無法刪除：{failed} 個。",
        "settings": "設定",
        "about": "關於 rgPDF",
        "about_title": "關於 rgPDF",
        "about_content": (
            "<h3>rgPDF {version}</h3>"
            "<p>Copyright © 2026 meebox</p>"
            "<p>本程式依 GNU Affero General Public License version 3 授權，"
            "不附帶任何擔保。你可以依該授權使用、研究、修改及重新散布。</p>"
            "<p><a href=\"https://github.com/codemee/rgpdf/tree/v{version}\">"
            "取得本版本原始碼</a> · "
            "<a href=\"https://github.com/codemee/rgpdf/blob/v{version}/LICENSE\">"
            "完整授權條款</a> · "
            "<a href=\"https://github.com/codemee/rgpdf/blob/v{version}/THIRD-PARTY-NOTICES.md\">"
            "第三方授權</a></p>"
        ),
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
        "converting_word": "正在轉換 Word 文件：{name}",
        "preparing_search": "正在準備搜尋…",
        "screening_word": "初篩 {current}/{total}：{name}；候選 Word {candidates} 份",
        "done": "完成：搜尋 {scanned} 份文件，{files} 份有結果，共 {matches} 筆命中",
        "cancelled": "搜尋已取消：已處理 {scanned} 份文件",
        "no_results": "找不到符合項目",
        "choose_folder": "選取文件資料夾",
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
        "previous_page": "上一頁",
        "next_page": "下一頁",
        "zoom_out": "縮小",
        "zoom_in": "放大",
        "fit": "符合寬度",
        "fit_page": "符合頁面",
        "page_single": "第 {start} 頁",
        "page_range": "第 {start}–{end} 頁",
        "match_count": "{count} 筆",
    },
    "en": {
        "app_title": "rgPDF {version} — Document Search",
        "folder": "Document folder",
        "stem_filter": "Filename stem filter",
        "stem_filter_hint": "e.g. ch0*; leave empty to search all stems",
        "stem_filter_help_title": "Filename stem filter help",
        "stem_filter_help_content": (
            "<b>Filename stem filter (Glob)</b><br>"
            "Leave empty for no filter. Matches the entire filename without its last extension, ignoring case; folder names are excluded.<br>"
            "• <code>*</code>: any string, including an empty string<br>"
            "• <code>?</code>: one character<br>"
            "• <code>[abc]</code>: one character from the set<br>"
            "• <code>[0-9]</code>: one character in the range<br>"
            "• <code>[!abc]</code>: one character outside the set<br>"
            "<b>Examples</b><br>"
            "• <code>ch0*</code>: matches ch01 and ch02, but not ch1 or ch2<br>"
            "• <code>ch0?</code>: matches ch01, but not ch001<br>"
            "• <code>ch0[1-3]</code>: matches ch01, ch02, and ch03<br>"
            "• <code>ch01</code>: matches only the exact stem ch01 (e.g. ch01.pdf or ch01.docx)<br>"
            "This field uses Glob syntax, independently of content search’s regular-expression and case settings."
        ),
        "stem_filter_help": "Match the filename without its extension, ignoring case. Supports * (any string), ? (one character), [abc], [0-9], and [!abc]. For example, ch0* matches ch01 and ch02, but not ch1 or ch2. Leave empty for no filter.",
        "file_types": "Search files",
        "scope_pdf": "PDF only",
        "scope_word": "Word only (DOC, DOCX)",
        "scope_all": "PDF and Word",
        "browse": "Browse…",
        "pattern": "Search pattern",
        "pattern_hint": "Enter text or a regular expression",
        "pattern_help": "Search pattern help",
        "pattern_help_content": (
            "<b>Search pattern</b><br>"
            "With Regular Expression off, the input is matched as literal text.<br>"
            "With it on, examples include:<br>"
            "• <code>example\\s*\\d+</code>: ‘example’, optional whitespace, then digits<br>"
            "• <code>error|warning</code>: either word<br>"
            "• <code>\\b[A-Z]{{2}}\\d{{4}}\\b</code>: two uppercase letters and four digits<br>"
            "Syntax reference: <a href=\"https://github.com/mrabarnett/mrab-regex#readme\">"
            "regex documentation</a>"
        ),
        "plain": "Plain text",
        "regex": "Regular Expression",
        "case": "Case sensitive",
        "recursive": "Include subfolders",
        "highlight_settings": "Highlight color",
        "common_colors": "Common colors",
        "custom_color": "Custom color…",
        "choose_highlight_color": "Choose highlight color",
        "clear_word_cache": "Clear Word cache",
        "clear_cache_confirm": "Delete every cached PDF created from Word documents? Original documents will not be deleted.",
        "cache_cleared_body": "Removed {count} cache files and freed {size} MB. Could not remove: {failed}.",
        "settings": "Settings",
        "about": "About rgPDF",
        "about_title": "About rgPDF",
        "about_content": (
            "<h3>rgPDF {version}</h3>"
            "<p>Copyright © 2026 meebox</p>"
            "<p>This program is licensed under the GNU Affero General Public License "
            "version 3 and comes with absolutely no warranty. You may use, study, "
            "modify, and redistribute it under that license.</p>"
            "<p><a href=\"https://github.com/codemee/rgpdf/tree/v{version}\">"
            "Source for this version</a> · "
            "<a href=\"https://github.com/codemee/rgpdf/blob/v{version}/LICENSE\">"
            "Full license</a> · "
            "<a href=\"https://github.com/codemee/rgpdf/blob/v{version}/THIRD-PARTY-NOTICES.md\">"
            "Third-party notices</a></p>"
        ),
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
        "converting_word": "Converting Word document: {name}",
        "preparing_search": "Preparing search…",
        "screening_word": "Screening {current}/{total}: {name}; Word candidates: {candidates}",
        "done": "Done: searched {scanned} documents, {files} files matched, {matches} matches",
        "cancelled": "Search cancelled after {scanned} documents",
        "no_results": "No matches found",
        "choose_folder": "Choose document folder",
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
        "previous_page": "Previous page",
        "next_page": "Next page",
        "zoom_out": "Zoom out",
        "zoom_in": "Zoom in",
        "fit": "Fit width",
        "fit_page": "Fit page",
        "page_single": "Page {start}",
        "page_range": "Pages {start}–{end}",
        "match_count": "{count} matches",
    },
}


def translate(language: str, key: str, **values: object) -> str:
    catalog = TRANSLATIONS.get(language, TRANSLATIONS["en"])
    return catalog.get(key, TRANSLATIONS["en"].get(key, key)).format(**values)
