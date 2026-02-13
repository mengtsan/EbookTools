# CosyAudiobook Factory (Mac Mini / MLX Edition) 🍎🔊

A fully offline, local AI audiobook generator optimized for Apple Silicon (M1/M2/M3/M4) using the MLX framework and the Fun-CosyVoice3 model.

## ✨ Features

*   **100% Offline & Private**: No data leaves your Mac. Your private library stays private.
*   **Hardware Accelerated**: Built on Apple's **MLX** framework to leverage the Neural Engine and GPU.
*   **Zero-Shot Voice Cloning**: Clone any voice from a 5-10 second audio sample.
*   **Smart Chapter Operations**:
    *   **Auto-TOC Detection**: Automatically skips Table of Contents, Copyright pages, and other non-story content.
    *   **Intelligent Text Splitting**: Handles long chapters by splitting text at natural pauses to avoid generation artifacts.
*   **Modern UI**: Beautiful, dark-mode web dashboard for managing the workflow.
*   **Standard Output**: Generates MP3 files with proper ID3 tags (Title, Artist, Album).

## 🛠 Prerequisites

*   **Hardware**: Mac with Apple Silicon (M1 or later).
*   **OS**: macOS Sequoia 15.0+ (recommended for latest Metal drivers).
*   **Software**:
    *   Python 3.10+
    *   `ffmpeg` (Required for audio processing)

### Installing FFmpeg
```bash
brew install ffmpeg
```

## 🚀 Installation

1.  **Clone/Setup Directory**
    ```bash
    mkdir CosyEbook && cd CosyEbook
    # (Copy project files here)
    ```

2.  **Create Virtual Environment**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

## 🏃‍♂️ Usage

1.  **Start the Server**
    ```bash
    source venv/bin/activate
    uvicorn app:app --host 0.0.0.0 --port 8000
    ```

2.  **Open the Dashboard**
    Open your browser to [http://localhost:8000](http://localhost:8000).

3.  **Generate Audiobook**
    1.  **Upload Voice**: Click the top-left box to upload a reference audio (WAV/MP3, ~10s of clean speech).
    2.  **Upload Ebook**: Drag & Drop your EPUB file into the bottom-left box.
    3.  **Select Chapters**: Use the right-hand panel to confirm which chapters to generate (Smart Filter handles the defaults).
    4.  **Start**: Click "Start Generation" and watch the progress.

    *Note: The first run will automatically download the ~2GB model weights from Hugging Face.*

## 📂 Project Structure

```
CosyEbook/
├── app.py                 # FastAPI Backend Server
├── requirements.txt       # Python Dependencies
├── core/                  # Core Logic Modules
│   ├── epub_parser.py     # EPUB Parsing & Smart Filtering
│   ├── tts_engine.py      # MLX CosyVoice3 Wrapper
│   └── audio_proc.py      # Audio Stitching & MP3 Export
├── static/                # Frontend Assets
│   └── index.html         # Web Dashboard
└── output/                # Generated Audiobooks (MP3s)
```

## 🔧 Troubleshooting

*   **Port 8000 already in use?**
    Run `pkill -f uvicorn` to stop old processes, or change the port in the start command.
*   **Model Download Fails?**
    Ensure you have an active internet connection for the initial setup. Subsequent runs are fully offline.
*   **"ModuleNotFoundError: mlx_audio"?**
    Ensure you activated the virtual environment (`source venv/bin/activate`).

## 📜 License
MIT License
