# CosyAudiobook 系統架構與開發建議書 (Issue R1)

## 1. 核心系統架構概觀

本專案主要由後端 FastAPI (`app.py`) 驅動，透過 `core/` 目錄下的模組協作完成兩大任務：**EPUB 電子書翻譯** 與 **有聲書製作 (TTS)**。

### A. 電子書翻譯架構 (EPUB Translation)

目前採用 **結構保留式 (Structure-Preserving)** 的翻譯策略，確保翻譯後電子書格式與原文完全一致。

1.  **EPUB 解析 (`core/epub_processor.py`)**
    *   **設計哲學**：不使用 `ebooklib` 重建，而是直接解壓 ZIP 並修改 HTML。
    *   **核心機制**：
        *   **XML 宣告保留**：手動提取並還原 `<?xml ... ?>`，避免閱讀器報錯。
        *   **白名單標籤提取**：僅提取 `<p>`, `<h1>`~`<h6>`, `<title>` 等區塊元素，**絕對不碰** `<a>` (連結) 或 `<div>` (容器)，以避免破壞導航與排版。
        *   **1:1 對應置換**：利用 `orig_paragraphs` 與 `trans_paragraphs` 的索引對應進行置換，不依賴文字搜尋，能完美處理重複句子。

2.  **翻譯引擎 (`core/translator_worker_mlx.py`)**
    *   **模型**：`m-i/HY-MT1.5-7B-mlx-8Bit` (專為小說優化)。
    *   **執行環境**：獨立 Process 運行於 `venv_mt15`，避免與主程式依賴衝突。
    *   **關鍵邏輯**：
        *   **逐段翻譯 (Strict 1:1)**：停用批次 (Batching)，確保輸入 N 段就輸出 N 段，避免因模型合併段落導致後續內容錯位（這曾是導致後半本未翻譯的主因）。
        *   **上下文記憶 (Context Awareness)**：傳遞前一段翻譯結果給模型，提升連貫性。
        *   **即時進度**：回傳章節內的百分比進度，解決長章節進度條卡住的問題。

### B. 音訊合成架構 (TTS Pipeline)

支援 **CosyVoice3** (自然度高) 與 **Qwen3-TTS** (指令控制強) 雙引擎。

1.  **文本切片 (`core/text_slicer.py`)**
    *   使用 `re` 根據標點符號 (`!?。`) 進行智慧切分，確保每一句長度適合 TTS 生成，避免模型崩潰或幻覺。

2.  **語音生成 (`core/tts_engine.py`)**
    *   **多引擎支援**：透過 `subprocess` 呼叫對應 venv (`venv_cosyvoice3`, `venv_qwen3`) 的 Worker。
    *   **零樣本複製 (Zero-Shot Cloning)**：
        *   這需要 3-10 秒的參考音訊 (`ref_audio`)。
        *   **CosyVoice3**：透過 `core/transcribe.py` (Whisper) 先轉錄參考音訊的文字，再進行 Prompt TTS，準確度極高。

3.  **音訊後處理 (`core/audio_merger.py`)**
    *   使用 `ffmpeg` 將生成的片段合併為單一章節音訊。
    *   自動正規化響度並轉換為 MP3/M4B。

---

## 2. 開發注意事項 (Critical Watchlist)

在後續維護或修改時，請務必注意以下「地雷區」：

1.  **EPUB 處理絕對不要用遞迴 (No Recursion)**
    *   不要嘗試遞迴遍歷 HTML 樹 (`walk()`)，因為不同書籍的巢狀結構不可預測（如 `<div><p><a>...</a></p></div>`）。
    *   **堅持扁平化處理**：只抓取頂層 Block Tags，這是最穩健的方法。

2.  **翻譯必須保持 1:1 (Strict 1:1 Mapping)**
    *   不要為了速度開啟 Batch Translation（把多行拼成一大段送給 AI）。
    *   AI 極易在輸出時合併或省略短句，導致回傳段落數 != 輸入段落數。
    *   一旦段落數不對齊，整章的翻譯就會錯位，甚至從中間開始變成原文。

3.  **依賴隔離 (Venv Isolation)**
    *   **MLX (翻譯)** 與 **Torch/CUDA (TTS)** 的依賴庫經常衝突。
    *   請維持目前的 `venv_mt15` (MLX), `venv_cosyvoice3` (Torch), `venv` (FastAPI) 分離架構，不要試圖合併環境。

4.  **XML 宣告不能丟**
    *   使用 `BeautifulSoup` 時，預設會吞掉 `<?xml version='1.0' ... ?>`。
    *   必須在 parse 前存起來，serialize 後手動加回去，否則 Apple Books 等嚴格閱讀器會報錯。

---

## 3. 未來優化建議 (Recommendations)

### 短期優化
*   **斷點續傳翻譯**：目前翻譯中斷需重頭開始。可將 `translated_chapters` 即時寫入 JSON，失敗後讀取以跳過已翻譯章節。
*   **翻譯快取 (Cache)**：建立 `source_hash -> translation` 的資料庫，避免對同一本書重複翻譯相同句子。

### 長期優化
*   **並行翻譯 (Parallel Translation)**：
    *   目前是單執行緒。MLX 在 M系列晶片上可以支援多 Batch，但受限於上下文記憶 (Context)，小說翻譯較難並行。
    *   可行方案：以「章節」為單位並行（需多個 Worker），但需注意記憶體 (RAM) 使用量。
*   **TTS 情感控制**：
    *   目前的 TTS 主要依賴參考音訊的語氣。
    *   可嘗試引入 LLM 分析文本情感 (如 `[Angry]`, `[Sad]`)，並動態切換不同的參考音訊。

---

> 文件版本：R1
> 更新日期：2026-02-15
