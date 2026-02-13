#!/bin/bash

# Get the directory where this script is located
cd "$(dirname "$0")"

echo "========================================"
echo "    CosyAudiobook 啟動器 (Mac版)"
echo "========================================"

# 1. Inspect Python
if ! command -v python3 &> /dev/null; then
    echo "錯誤: 未偵測到 Python 3。"
    echo "請從 https://www.python.org/downloads/macos/ 下載並安裝 Python 3。"
    read -p "按 Enter 鍵退出..."
    exit 1
fi

# 2. Inspect FFmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo "警告: 未偵測到 FFmpeg。"
    echo "本程式需要 FFmpeg 才能處理音訊。"
    echo "嘗試自動安裝 (需要 Homebrew)..."
    if command -v brew &> /dev/null; then
        brew install ffmpeg
    else
        echo "錯誤: 未安裝 Homebrew，無法自動安裝 FFmpeg。"
        echo "請手動安裝 FFmpeg: brew install ffmpeg"
        read -p "按 Enter 鍵退出..."
        exit 1
    fi
fi

# 3. Setup Virtual Environments

echo "檢查運行環境..."

# 3.1 Main Environment (Qwen3 + API)
if [ ! -d "venv" ]; then
    echo "正在建立主虛擬環境 (1/2)..."
    python3 -m venv venv
    
    # Upgrade pip in venv
    ./venv/bin/pip install --upgrade pip
    
    echo "正在安裝主環境套件 (Qwen3 & API)..."
    ./venv/bin/pip install -r requirements.txt
    
    if [ $? -ne 0 ]; then
        echo "錯誤: 主環境套件安裝失敗。"
        read -p "按 Enter 鍵退出..."
        exit 1
    fi
else
    echo "- 主環境已存在"
fi

# 3.2 CosyVoice3 Environment
if [ ! -d "venv_cosyvoice3" ]; then
    echo "正在建立 CosyVoice3 虛擬環境 (2/2)..."
    python3 -m venv venv_cosyvoice3
else
    echo "- CosyVoice3 虛擬環境已存在"
fi

# Always check/install dependencies to ensure they are up to date and fixed
echo "正在檢查/更新 CosyVoice3 套件..."
# Upgrade pip/wheel first
./venv_cosyvoice3/bin/pip install --upgrade pip setuptools wheel > /dev/null 2>&1

# Pre-install build dependencies (quietly)
./venv_cosyvoice3/bin/pip install "MarkupSafe>=2.1.3" "Jinja2>=3.1.3" > /dev/null 2>&1

# Install main requirements (no cache to avoid corrupted/stale wheels)
./venv_cosyvoice3/bin/pip install --no-cache-dir -r requirements_cosy.txt

# Install mlx-audio-plus WITHOUT its dependencies (--no-deps)
# CosyVoice3 model lives in mlx-audio-plus, NOT in mlx-audio itself.
# mlx-audio-plus has conflicting dep requirements (mlx-lm<0.30, transformers<5),
# but the actual model code works fine with our pinned versions.
./venv_cosyvoice3/bin/pip install --no-deps --no-cache-dir 'mlx-audio-plus==0.1.8'

# Force install critical packages that pip backtracking may drop
./venv_cosyvoice3/bin/pip install scipy sounddevice mlx-whisper mlx-lm

# VERIFY ENVIRONMENT
echo "正在驗證環境完整性..."
./venv_cosyvoice3/bin/python core/verify_env_cosy.py
if [ $? -ne 0 ]; then
    echo "警告: 環境驗證失敗，正在嘗試修復..."
    echo "嘗試強制重新安裝關鍵套件 (無快取)..."
    ./venv_cosyvoice3/bin/pip install --force-reinstall --no-cache-dir 'mlx-audio==0.3.1' 'mlx-audio-plus==0.1.8' --no-deps
    ./venv_cosyvoice3/bin/pip install --force-reinstall --no-cache-dir scipy sounddevice mlx-whisper mlx-lm
    
    # Verify again
    ./venv_cosyvoice3/bin/python core/verify_env_cosy.py
    if [ $? -ne 0 ]; then
        echo "嚴重錯誤: 無法修復 environment。請聯繫開發者。"
        read -p "按 Enter 鍵退出..."
        exit 1
    fi
    echo "環境修復成功！"
else
    echo "環境驗證通過！"
fi

echo "環境設定完成！"

# 4. Start Server
echo "正在啟動伺服器..."
echo "網址: http://localhost:8000"
echo "請勿關閉此視窗，否則服務將停止。"

# Open browser in background after a slight delay
(sleep 3 && open http://localhost:8000) &

# Run uvicorn using the MAIN venv
./venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000

read -p "服務已停止。按 Enter 鍵退出..."
