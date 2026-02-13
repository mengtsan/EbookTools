# CosyAudiobook 🍎🔊

EPUB 有聲書生成器 — 專為 Apple Silicon 優化，使用 MLX 框架與 CosyVoice3 / Qwen3 TTS 模型。

## ✨ Features

- **100% 離線 & 隱私**: 資料不離開你的 Mac
- **硬體加速**: 基於 Apple MLX 框架，發揮 Neural Engine 與 GPU 效能
- **聲音克隆 (Zero-Shot)**: 只需 5-10 秒參考音訊即可克隆任意聲音
- **雙 TTS 引擎**: 支援 CosyVoice3（聲音克隆）與 Qwen3（內建音色）
- **智慧章節處理**: 自動跳過目錄、版權頁等非正文內容
- **EPUB 翻譯**: 內建翻譯功能（日→中、英→中 等）
- **語音設計師**: 自訂音色生成
- **現代 Web UI**: 深色模式控制面板，即時進度追蹤

## 🛠 Prerequisites

- **硬體**: Mac with Apple Silicon (M1 或更新)
- **系統**: macOS Sequoia 15.0+
- **軟體**: Python 3.10+、FFmpeg

```bash
# 安裝 FFmpeg
brew install ffmpeg
```

## 🚀 Quick Start

### 方法一：Mac Portable（推薦）
1. 下載 `CosyAudiobook_Mac_Portable.zip`
2. 解壓縮後雙擊 `start_app.command`
3. 瀏覽器會自動開啟 http://localhost:8000

### 方法二：從原始碼安裝
```bash
git clone https://github.com/mengtsan/EbookTools.git
cd EbookTools
chmod +x start_app.command
./start_app.command
```

> **首次啟動**會自動建立虛擬環境並安裝所有依賴，需要幾分鐘。
> 之後的啟動會跳過安裝步驟，幾秒即可啟動。

## 📖 Usage

1. 開啟 http://localhost:8000
2. **上傳語音**: 上傳參考音訊（WAV/MP3，約 10 秒清晰語音）
3. **上傳電子書**: 拖放 EPUB 檔案
4. **選擇章節**: 確認要生成的章節
5. **開始生成**: 點擊「開始生成」

> 首次執行會自動從 Hugging Face 下載模型（約 2GB），之後完全離線運作。

## 📂 Project Structure

```
EbookTools/
├── app.py                      # FastAPI 後端伺服器
├── start_app.command            # Mac 一鍵啟動腳本
├── package_for_release.sh       # 打包發行腳本
├── requirements.txt             # 主環境依賴 (Qwen3 + API)
├── requirements_cosy.txt        # CosyVoice3 環境依賴
├── VERSION                      # 版本號
├── core/                        # 核心模組
│   ├── tts_engine.py            # TTS 引擎調度
│   ├── tts_cosyvoice3.py        # CosyVoice3 TTS Worker
│   ├── tts_qwen3.py             # Qwen3 TTS Worker
│   ├── epub_parser.py           # EPUB 解析
│   ├── epub_writer.py           # EPUB 寫入
│   ├── translator.py            # 翻譯引擎
│   ├── voice_design.py          # 語音設計
│   ├── audio_proc.py            # 音訊處理
│   ├── transcribe.py            # 語音轉文字
│   └── verify_env_cosy.py       # 環境完整性驗證
└── static/
    └── index.html               # Web UI
```

## 🔧 Troubleshooting

| 問題 | 解決方案 |
|------|---------|
| Port 8000 被佔用 | `pkill -f uvicorn` 或修改啟動指令的 port |
| 模型下載失敗 | 確保有網路連線（僅首次需要） |
| `No module named 'einops'` | 刪除 `venv_cosyvoice3` 資料夾後重啟 |
| pip 安裝異常 | 執行 `pip cache purge` 清除快取後重試 |
| 生成 0 bytes 檔案 | 檢查 `install.log` 中的錯誤訊息 |

## 📜 License
MIT License
