#!/bin/bash

# Get the directory where this script is located
cd "$(dirname "$0")"

VERSION=$(cat VERSION 2>/dev/null || echo "unknown")
echo "========================================"
echo "  CosyAudiobook v${VERSION} 啟動器 (Mac版)"
echo "========================================"

# ---------- Helper: compute requirements checksum ----------
compute_req_hash() {
    cat requirements.txt requirements_cosy.txt 2>/dev/null | shasum -a 256 | cut -c1-16
}

# ---------- 1. Inspect Python ----------
if ! command -v python3 &> /dev/null; then
    echo "錯誤: 未偵測到 Python 3。"
    echo "請從 https://www.python.org/downloads/macos/ 下載並安裝 Python 3。"
    read -p "按 Enter 鍵退出..."
    exit 1
fi

# ---------- 2. Inspect FFmpeg ----------
if ! command -v ffmpeg &> /dev/null; then
    echo "警告: 未偵測到 FFmpeg。"
    echo "嘗試自動安裝 (需要 Homebrew)..."
    if command -v brew &> /dev/null; then
        brew install ffmpeg
    else
        echo "錯誤: 未安裝 Homebrew，無法自動安裝 FFmpeg。"
        echo "請手動安裝: brew install ffmpeg"
        read -p "按 Enter 鍵退出..."
        exit 1
    fi
fi

# ---------- 3. Setup Virtual Environments ----------

REQ_HASH=$(compute_req_hash)
INSTALL_LOG="install.log"

# 3.1 Main Environment (Qwen3 + API)
MAIN_MARKER="venv/.installed_${REQ_HASH}"
if [ -f "$MAIN_MARKER" ]; then
    echo "✅ 主環境已就緒 (cached)"
else
    echo "正在建立主虛擬環境 (1/2)..."
    
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    
    echo "  安裝主環境套件 (Qwen3 & API)..."
    {
        ./venv/bin/pip install --upgrade pip
        ./venv/bin/pip install -r requirements.txt
    } > "$INSTALL_LOG" 2>&1
    
    if [ $? -ne 0 ]; then
        echo "❌ 主環境套件安裝失敗。詳見 $INSTALL_LOG"
        read -p "按 Enter 鍵退出..."
        exit 1
    fi
    
    # Clear old markers and set new one
    rm -f venv/.installed_* 2>/dev/null
    touch "$MAIN_MARKER"
    echo "✅ 主環境安裝完成"
fi

# 3.2 CosyVoice3 Environment
COSY_MARKER="venv_cosyvoice3/.installed_${REQ_HASH}"
if [ -f "$COSY_MARKER" ]; then
    echo "✅ CosyVoice3 環境已就緒 (cached)"
else
    echo "正在建立 CosyVoice3 虛擬環境 (2/2)..."
    
    if [ ! -d "venv_cosyvoice3" ]; then
        python3 -m venv venv_cosyvoice3
    fi
    
    echo "  安裝 CosyVoice3 套件 (可能需要幾分鐘)..."
    {
        # Upgrade pip/wheel first
        ./venv_cosyvoice3/bin/pip install --upgrade pip setuptools wheel
        
        # Pre-install build dependencies
        ./venv_cosyvoice3/bin/pip install "MarkupSafe>=2.1.3" "Jinja2>=3.1.3"
        
        # Install main requirements (no cache to avoid corrupted/stale wheels)
        ./venv_cosyvoice3/bin/pip install --no-cache-dir -r requirements_cosy.txt
        
        # Install mlx-audio-plus WITHOUT its dependencies (--no-deps)
        # CosyVoice3 model lives in mlx-audio-plus, NOT in mlx-audio itself.
        ./venv_cosyvoice3/bin/pip install --no-deps --no-cache-dir 'mlx-audio-plus==0.1.8'
    } > "$INSTALL_LOG" 2>&1
    
    if [ $? -ne 0 ]; then
        echo "❌ CosyVoice3 套件安裝失敗。詳見 $INSTALL_LOG"
        read -p "按 Enter 鍵退出..."
        exit 1
    fi
    echo "✅ CosyVoice3 套件安裝完成"
fi

# ---------- 4. Verify CosyVoice3 Environment ----------
echo "正在驗證環境完整性..."
./venv_cosyvoice3/bin/python core/verify_env_cosy.py 2>&1
if [ $? -ne 0 ]; then
    echo ""
    echo "⚠️  環境驗證失敗，正在嘗試修復..."
    {
        ./venv_cosyvoice3/bin/pip install --force-reinstall --no-cache-dir 'mlx-audio==0.3.1'
        ./venv_cosyvoice3/bin/pip install --no-deps --no-cache-dir 'mlx-audio-plus==0.1.8'
        ./venv_cosyvoice3/bin/pip install --no-cache-dir scipy sounddevice mlx-whisper mlx-lm einops
    } >> "$INSTALL_LOG" 2>&1
    
    # Verify again
    ./venv_cosyvoice3/bin/python core/verify_env_cosy.py 2>&1
    if [ $? -ne 0 ]; then
        echo "❌ 無法修復環境。詳見 $INSTALL_LOG"
        echo "   提示: 嘗試刪除 venv_cosyvoice3 資料夾後重新啟動"
        # Remove marker to force reinstall next time
        rm -f venv_cosyvoice3/.installed_* 2>/dev/null
        read -p "按 Enter 鍵退出..."
        exit 1
    fi
    echo "✅ 環境修復成功！"
else
    # Verification passed — mark as installed
    rm -f venv_cosyvoice3/.installed_* 2>/dev/null
    touch "$COSY_MARKER"
    echo "✅ 環境驗證通過"
fi

echo ""
echo "========================================" 
echo "  環境設定完成！正在啟動伺服器..."
echo "========================================"
echo "  網址: http://localhost:8000"
echo "  請勿關閉此視窗"
echo ""

# Open browser in background after a slight delay
(sleep 3 && open http://localhost:8000) &

# Run uvicorn using the MAIN venv
./venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000

read -p "服務已停止。按 Enter 鍵退出..."
