# CosyAudiobook v0.2.0 - 系統架構與注意事項 (Issue Log)

此文件紀錄目前的系統架構設計決策、已知的依賴問題以及未來的潛在改進方向。

## 1. 系統架構設計 (System Architecture)

### 1.1 雙虛擬環境設計 (Dual-venv Strategy)
目前的系統運作依賴兩個獨立的 Python 虛擬環境，這是為了避開依賴衝突：

*   **`venv` (Main API)**: 
    *   負責主程式 `app.py`、Web UI、EPUB 解析、翻譯模組。
    *   主要依賴：`FastAPI`, `Uvicorn`, `ebooklib`, `BeautifulSoup`。
    *   包含 **Qwen3 TTS** (因為它的依賴較單純，不衝突)。

*   **`venv_cosyvoice3` (Worker)**:
    *   專門負責 **CosyVoice3** 的推論。
    *   主要依賴：`mlx-audio`, `mlx-audio-plus` (模型來源), `mlx-lm`, `einops`。
    *   **衝突點**：`mlx-audio-plus==0.1.8` 強制要求舊版的 `transformers<5.0.0` 和 `mlx-lm<0.30.0`，這與其他現代套件衝突。我們採用了 `--no-deps` 的特殊安裝策略來繞過此限制。

### 1.2 進程間通訊 (IPC)
*   主程式 (`venv`) 透過 `subprocess.Popen` 呼叫 `venv_cosyvoice3` 中的 Worker 腳本。
*   通訊方式：標準輸入/輸出 (stdin/stdout)。
*   資料格式：JSON 訊息流 (Streaming JSON)。
    *   Worker 輸出每一行都是一個完整的 JSON 物件（包含 `status`, `message`, `progress` 等）。
    *   任何非 JSON 的輸出（如 stderr 的報錯）會被主程式擷取並記錄到日誌，避免破壞 API 回應。

## 2. 關鍵實作細節與 workaround

### 2.1 CosyVoice3 模型注入 (Model Injection)
*   **問題**：標準的 `pip install mlx-audio` PyPI 包**不包含** CosyVoice3 模型定義檔。即使安裝了也無法使用。
*   **解法**：我們利用 `mlx-audio-plus` 套件，它包含了模型定義。
*   **特殊安裝**：
    ```bash
    pip install --no-deps mlx-audio-plus==0.1.8
    ```
    這會把模型檔案注入到 `site-packages/mlx_audio/tts/models/cosyvoice3`，讓標準的 `mlx_audio` 也能讀取到模型。

### 2.2 遺失的依賴 (Missing Dependencies)
*   **`einops`**: `mlx-audio` 的 PyPI 包依賴列表中漏掉了 `einops`，導致執行時會報錯 `No module named 'einops'`。
*   **解決**：必須顯式在 `requirements_cosy.txt` 或安裝腳本中加入 `einops`。
*   **驗證**：`core/verify_env_cosy.py` 已加入對 `einops` 的檢查。

### 2.3 啟動優化 (Startup Optimization)
*   **Marker File**: 為了避免每次啟動都重新跑 pip install（很慢），`start_app.command` 會檢查 `.installed_{hash}` 檔案。
*   **Checksum**: Hash 值由 `requirements.txt` + `requirements_cosy.txt` 的內容計算得出。只要修改了依賴檔，下次啟動就會自動觸發重新安裝。

## 3. 已知限制與潛在問題 (Known Issues)

### 3.1 模型下載體積
*   CosyVoice3 模型 + Qwen3 模型首次執行需要下載約 **2GB - 3GB** 的權重檔。
*   **風險**：若用戶網路不穩，下載中斷可能會導致 Hugging Face cache 損壞。
*   **解法**：目前依賴 `huggingface_hub` 自動處理，若失敗需手動清除 cache (`~/.cache/huggingface`)。

### 3.2 冷啟動時間 (Cold Start)
*   CosyVoice3 模型載入需要約 5-10 秒（視記憶體頻寬而定）。
*   目前設計是 **Lazy Loading**（第一次請求生成時才載入），這會導致點擊「開始」後第一句回應較慢。

### 3.3 記憶體佔用
*   雙 TTS 引擎若同時開啟，加上 Web API，建議至少需要 **16GB 統一記憶體**。
*   8GB 機型可能會因為 Swap 而變慢，雖可執行但不建議多工操作。

## 4. 未來優化方向 (TODOs)

1.  **整合單一環境**：
    *   等待 `mlx-audio` 或 `mlx-audio-plus` 更新，解決版本依賴衝突後，可嘗試合併回單一 venv，減少磁碟佔用（目前約 1.5GB -> 800MB）。
2.  **模型量化 (Quantization)**：
    *   目前使用預設精度（通常是 float16/bfloat16）。若能支援 4-bit 量化，可大幅降低記憶體需求。
3.  **串流播放 (Streaming Playback)**：
    *   目前 Web UI 是等待單句生成完畢後才回傳進度。未來可改為 WebSocket 真·串流音訊回傳，實現「邊聽邊生成」。
4.  **自動更新 (Auto Update)**：
    *   加入 `git pull` 機制或簡單的版本檢查 API，提示用戶有新版本。

---
*Last Updated: v0.2.0*
