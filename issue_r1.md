# CosyAudiobook 系統架構與開發建議書 (Issue R3)

## 1. 核心系統架構概觀

本專案由 FastAPI (`app.py`, 514 行) 驅動，透過 `core/` 下 12 個模組完成三大功能：

| 功能 | 核心模組 | 虛擬環境 |
|------|---------|---------|
| 有聲書製作 (TTS) | `tts_engine.py`, `tts_cosyvoice3.py`, `tts_qwen3.py` | `venv_cosyvoice3`, `venv_qwen3` |
| EPUB 翻譯 | `translator_mlx.py`, `translator_worker_mlx.py` | `venv_mt15` |
| 聲音設計 | `voice_design.py`, `voice_design_worker.py` | `venv_qwen3` |

**共通基礎模組**：`text_slicer.py` (文本切片), `audio_merger.py` (音訊合併), `epub_processor.py` (EPUB 處理), `transcribe.py` (語音辨識)

### A. 電子書翻譯架構 (EPUB Translation)

採用 **結構保留式 (Structure-Preserving)** 策略，直接操作 ZIP 內的 HTML。

1.  **EPUB 解析 (`core/epub_processor.py`)**
    *   **設計哲學**：不使用 `ebooklib` 重建，直接解壓 ZIP 並修改 HTML。
    *   **核心機制**：
        *   **XML 宣告保留**：手動提取並還原 `<?xml ... ?>`
        *   **白名單標籤**：僅提取 `<p>`, `<h1>`~`<h6>`, `<title>`，**不碰** `<a>` 或 `<div>`
        *   **1:1 索引置換**：用索引對應進行置換，不依賴文字搜尋

2.  **翻譯引擎 (`core/translator_worker_mlx.py`)**
    *   **模型**：`m-i/HY-MT1.5-7B-mlx-8Bit`
    *   **執行環境**：獨立 Process 運行於 `venv_mt15`
    *   **關鍵邏輯**：
        *   **逐段翻譯 (Strict 1:1)**：停用批次，確保 N 段輸入 = N 段輸出
        *   **上下文記憶**：傳遞前段翻譯結果給模型
        *   **即時進度**：回傳章節內百分比

### B. 音訊合成架構 (TTS Pipeline)

支援 **CosyVoice3** (自然度高) 與 **Qwen3-TTS** (指令控制強) 雙引擎。

1.  **文本切片 (`core/text_slicer.py`)** — 3 層智慧切分 (段落 → 合併短句 → 標點斷句)
2.  **語音生成 (`core/tts_engine.py`)** — 透過 `subprocess` 呼叫對應 venv 的 Worker
3.  **音訊後處理 (`core/audio_merger.py`)** — ffmpeg 合併 WAV → MP3，含 `stdin=DEVNULL` 防死鎖

### C. 前端 (`static/index.html`)

單檔 Vue.js 3 應用 (703 行)，三個頁籤：有聲書製作 / 聲音設計師 / EPUB 翻譯。
使用 CDN 載入 Vue.js、Tailwind CSS、Google Fonts。

---

## 2. 開發注意事項 (Critical Watchlist)

| # | 規則 | 說明 |
|---|------|------|
| 1 | **EPUB 不用遞迴** | 不要 `walk()` 遍歷 HTML 樹，只抓頂層 Block Tags |
| 2 | **翻譯保持 1:1** | 不開 Batch Translation，AI 會合併/省略短句導致錯位 |
| 3 | **依賴隔離** | 維持 `venv` / `venv_mt15` / `venv_cosyvoice3` / `venv_qwen3` 分離 |
| 4 | **XML 宣告不能丟** | BeautifulSoup 會吞掉 `<?xml ...?>`，須手動保留 |
| 5 | **子進程必加 `stdin=DEVNULL`** | 防止後台執行時 `SIGTTIN` 暫停導致死鎖 |
| 6 | **子進程必設 `timeout`** | 防止無限期卡住 Worker Thread |

---

## 3. 故障排除經驗 (Troubleshooting)

### 個案 A：伺服器卡死 (Server Deadlock)
*   **症狀**：卡在 "Processing: Cover"，網頁無回應
*   **根因**：`ffmpeg` 在後台執行時嘗試讀取 TTY → `SIGTTIN` → 進程暫停 → 主程 `wait()` 死鎖
*   **修正**：`subprocess.run(..., stdin=subprocess.DEVNULL, timeout=120)`

### 個案 B：任務失敗 (ffmpeg file not found)
*   **症狀**：ffmpeg 報錯 `Impossible to open '...chunk_0000.wavn'`
*   **根因**：concat list 的 `f.write()` 用了 `\\n` (字面反斜線 n) 而非 `\n` (換行)
*   **修正**：確認 `f.write(f"file '{path}'\n")` 中的 `\n` 是真正的換行符

---

## 4. 改進建議 (Improvement Proposals)

### 🔴 高優先 — 穩定性與可靠性

#### 4.1 子進程 `stdin=DEVNULL` 全面補齊
**影響範圍**：`translator_mlx.py` (L64), `voice_design.py` (L57)
這兩個模組的 `subprocess.Popen()` 呼叫目前**缺少** `stdin=subprocess.DEVNULL`。
與 `audio_merger.py` 遇到的死鎖問題完全相同，只是還沒觸發而已。

```python
# translator_mlx.py L64 — 目前
process = subprocess.Popen([...], stdout=subprocess.PIPE, stderr=subprocess.PIPE, ...)

# 應改為
process = subprocess.Popen([...], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           stdin=subprocess.DEVNULL, ...)
```

#### 4.2 移除廢棄的 `MLXEngine` 包裝層
`app.py` 透過 `MLXEngine` (deprecated wrapper) 間接存取 `SubprocessTTSEngine`，
甚至需要 `engine = tts_engine._subprocess_engine` 直接取出內部物件 (L319)。
**建議**：直接使用 `SubprocessTTSEngine`，刪除 `MLXEngine` 類別。

#### 4.3 任務狀態持久化
目前 `tasks = {}` 和 `translation_tasks = {}` 存在記憶體中，伺服器重啟即全部遺失。
**建議**：改用 SQLite 或 JSON 檔案儲存，支援斷點續傳。

---

### 🟡 中優先 — 效能與維護性

#### 4.4 `app.py` 拆分 (514 行 → 模組化)
目前所有 API Routes、業務邏輯、任務處理全在同一個檔案。
**建議拆分為**：
*   `routes/tts.py` — 有聲書相關 API
*   `routes/translation.py` — 翻譯相關 API
*   `routes/voice_design.py` — 聲音設計 API
*   `services/task_manager.py` — 任務狀態管理

#### 4.5 日誌系統標準化
目前用 `print(..., flush=True)` 做日誌 (含 `TRACE:`, `DEBUG:`, `ERROR:` 前綴)。
`server.log` 已累積至 **2MB**，無輪替機制。
**建議**：
*   改用 Python `logging` 模組 (支援層級過濾)
*   加入 `RotatingFileHandler` (限制單檔 5MB，保留 3 份)

#### 4.6 暫存檔清理
| 目錄 | 大小 | 問題 |
|------|------|------|
| `temp_chunks/` | 924KB | 包含 22 個歷史任務的殘留資料夾 |
| `uploads/` | 27MB | 含歷史上傳的 EPUB 和語音檔 |
| `debug_toc/` | 1.7MB | 除錯用 TOC 資料，應可刪除 |
| `server.log` | 2MB | 無輪替，會持續增長 |

**建議**：加入啟動時自動清理策略或定期排程。

---

### 🟢 低優先 — 體驗優化

#### 4.7 前端離線化
目前依賴 CDN 載入 Vue.js、Tailwind CSS、Google Fonts。
離線環境 (如無網路的 Mac) 會導致頁面完全無法渲染。
**建議**：將 JS/CSS 下載到 `static/vendor/` 本地載入。

#### 4.8 前端元件化
`index.html` 目前 703 行，所有頁面邏輯都在一個檔案中。
**建議**：拆分為 Vue SFC 或至少分出獨立 JS 檔。

#### 4.9 章節跳過策略優化
`process_book_task` 依賴 `os.path.getsize(out_path) > 1024` 判斷是否跳過。
如果前次生成了損壞的檔案 (>1KB 但音訊不完整)，會永遠被跳過。
**建議**：加入 MD5/SHA 校驗或用 ffprobe 驗證音訊完整性。

#### 4.10 `start_app.command` 缺少 `venv_mt15` 和 `venv_qwen3` 初始化
啟動腳本只建立 `venv` 和 `venv_cosyvoice3`，缺少翻譯環境 `venv_mt15` 和 Qwen3 TTS 環境 `venv_qwen3` 的自動安裝流程。
**建議**：補齊所有 4 個 venv 的自動化建置。

---

## 5. 專案檔案清單 (File Inventory)

### 核心程式碼 (12 files in `core/`)
| 檔案 | 行數 | 用途 |
|------|------|------|
| `tts_engine.py` | 422 | TTS 引擎主控 (含已廢棄 MLXEngine) |
| `epub_processor.py` | 354 | EPUB 結構保留翻譯 |
| `translator_worker_mlx.py` | ~200 | MLX 翻譯 Worker (subprocess) |
| `translator_mlx.py` | 123 | MLX 翻譯器介面 |
| `text_slicer.py` | 141 | 3 層文本智慧切片 |
| `audio_merger.py` | 167 | ffmpeg 音訊合併 |
| `voice_design.py` | 110 | 聲音設計 (Qwen3 VoiceDesign) |
| `voice_design_worker.py` | ~80 | 聲音設計 Worker |
| `tts_cosyvoice3.py` | ~80 | CosyVoice3 TTS Worker |
| `tts_qwen3.py` | ~100 | Qwen3-TTS Worker |
| `transcribe.py` | ~40 | Whisper 語音辨識 |
| `verify_env_cosy.py` | ~50 | CosyVoice3 環境驗證 |

### 其他重要檔案
| 檔案 | 用途 |
|------|------|
| `app.py` (514 行) | FastAPI 主程式 (路由 + 業務邏輯) |
| `static/index.html` (703 行) | 前端全部程式碼 |
| `start_app.command` (152 行) | Mac 啟動腳本 |
| `novel_translate.py` | 獨立命令列翻譯工具 |

---

> 文件版本：R3
> 更新日期：2026-02-17
