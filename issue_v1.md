# CosyAudiobook v0.3.0 - 系統架構與開發狀態 (System Status)

此文件紀錄目前的系統架構設計 (v0.3.0)、已實作功能以及開發注意事項。舊有資訊已移除。

## 1. 核心架構 (Core Architecture)

### 1.1 雙虛擬環境設計 (Dual-venv)
為了解決依賴衝突，系統運作於兩個獨立環境：
*   **`venv` (Main)**:
    *   負責 API (FastAPI), Web UI, EPUB 解析, Qwen3-TTS 推論。
    *   主要依賴: `mlx-audio`, `ffmpeg-python`, `ebooklib`, `fastapi`.
*   **`venv_cosyvoice3` (Worker)**:
    *   專門負責 **CosyVoice3** 推論 (因 `mlx-audio-plus` 依賴衝突)。
    *   被主程式透過 `subprocess` 呼叫。

### 1.2 智能切分與重組 (Smart Slicer & Merger)
為了解決長文本導致的「注意力崩潰 (Attention Collapse)」與 M4 記憶體問題，採用「分段生成 + 後期重組」策略：

1.  **文字切分 (`core/text_slicer.py`)**:
    *   **Tier 1**: 以換行符 `\n` 切分段落。
    *   **Tier 2 (Merge)**: 過短段落 (< 10 字) 自動合併至前一段，避免語音破碎。
    *   **Tier 3 (Split)**: 過長段落 (> 300/500 字) 強制在標點符號 (`。！？`) 處切分。
    *   **Cleaning**: Regex 自動移除 `*`, `#`, `---` 等 Markdown 雜訊。

2.  **斷點續傳 (`core/tts_engine.py`)**:
    *   生成時以 **Chunk** (段落) 為單位，存檔為 `temp_chunks/{task_id}/ch_{idx}/chunk_{XXXX}.wav`。
    *   **Fault Tolerance**: 若程式崩潰，重跑時會自動跳過已存在的有效 Chunk (`Skip Existing`)。

3.  **音訊重組 (`core/audio_merger.py`)**:
    *   使用 `ffmpeg-python` 將 Chunk 合併。
    *   **Silence Padding**: 每個 Chunk 之間插入 **300ms 靜音**，確保語速自然。
    *   合併完成後自動清除暫存檔。

### 1.3 M4 效能優化 (Apple Silicon Optimization)
針對 Mac M4 晶片的特別調優：
*   **GC & Cache**: 每生成 10 個 Chunks 執行一次 `gc.collect()` 與 `torch.mps.empty_cache()`，防止 unified memory 爆滿。
*   **FP16**: 模型載入強制使用 FP16 (若支援)。
*   **Fixed Seed**: 固定隨機種子 (`seed=42`) 以確保同一段落重跑時語調一致。

## 2. 目前狀態 (Current Status)

| 元件 | 狀態 | 備註 |
|:---|:---:|:---|
| **CosyVoice3** | ✅ 正常 | 需使用 `venv_cosyvoice3`，支援 Zero-shot Voice Cloning (需 Ref Audio) |
| **Qwen3-TTS** | ✅ 正常 | 運行於 Main venv，支援 Voice Cloning (需 Ref Audio + Ref Text) |
| **EPUB Parser** | ✅ 正常 | 支援章節過濾、智慧跳過 (目錄/版權頁) |
| **Web UI** | ✅ 正常 | 支援進度條、日誌顯示、斷點續傳 |

## 3. 已知問題與注意事項 (Known Issues & Notes)

### 3.1 Qwen3 的 Voice Cloning 限制
*   **問題**: Qwen3 使用 `mlx_audio`，若未提供 `ref_text`，它會嘗試內部 Whisper 轉錄。若轉錄失敗 (如環境問題)，會導致 `Processor not found` 崩潰。
*   **現狀 (Fix applied)**: 
    1. 系統會嘗試用 CosyVoice3 env 進行轉錄。
    2. 若轉錄失敗，Qwen3 Worker 會自動**降級**：捨棄 Ref Audio，改用預設音色生成 (避免崩潰)。

### 3.2 外部依賴 (External Dependencies)
*   **FFmpeg**: 系統依賴系統層級的 `ffmpeg` 指令進行音訊合併。
    *   必須安裝: `brew install ffmpeg`
    *   若未安裝，會在啟動時警告，且最後合併步驟會失敗。

### 3.3 句子截斷風險
*   若單一句子長度超過 `max_chars` (300/500) 且**完全沒有標點符號**，TextSlicer 會被迫硬切分 (Hard Split)，可能導致語句在不自然的地方中斷並插入 300ms 靜音。(目前機率低，暫不處理)

## 4. 開發指引 (Dev Guide)

*   **啟動伺服器**: `./start_app.command` (會自動檢查依賴)
*   **手動測試 Slicer**: `python3 test_text_slicer.py`
*   **手動測試 Merger**: `python3 test_audio_merger.py` (需 ffmpeg)
*   **查看錯誤日誌**: `backend_error.log` (主程式), `chunk_error.log` (Worker)

---
*Last Updated: v0.3.0*
