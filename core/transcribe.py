#!/usr/bin/env python3
"""
Transcription Helper Script
Uses mlx-audio-plus (from venv_cosyvoice3) to transcribe audio.
Used to generate ref_text for Qwen3-TTS to avoid dependency issues.
"""
import sys
import json
import os

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: transcribe.py <json_params>"}), flush=True)
        sys.exit(1)
    
    try:
        params = json.loads(sys.argv[1])
        audio_path = params.get("audio_path")
        
        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
            
        # Use mlx_whisper directly for stability
        import mlx_whisper
        
        print(json.dumps({"status": "transcribing", "message": "Transcribing audio..."}), flush=True)
        
        # Transcribe directly
        # mlx_whisper handles model loading automatically
        result = mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo="mlx-community/whisper-large-v3-mlx"
        )
        
        text = result.get("text", "").strip()
        
        print(json.dumps({"status": "completed", "text": text}), flush=True)
        
    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
