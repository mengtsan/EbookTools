#!/usr/bin/env python3
"""
Qwen3-TTS Worker Script
Uses mlx-audio to generate audio from text.
Called via subprocess from the main app.
"""
import sys
import json
import os

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: tts_qwen3.py <json_params>"}))
        sys.exit(1)
    
    try:
        params = json.loads(sys.argv[1])
        text = params.get("text", "")
        ref_audio = params.get("ref_audio")
        output_path = params.get("output_path", "output.wav")
        model_id = params.get("model_id", "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16")
        
        from mlx_audio.tts.generate import generate_audio
        from mlx_audio.tts.utils import load_model
        
        print(json.dumps({"status": "loading", "message": "Loading Qwen3-TTS model..."}), flush=True)
        model = load_model(model_id)
        
        print(json.dumps({"status": "generating", "message": f"Generating audio for: {text[:50]}..."}), flush=True)
        
        # Prepare args
        kwargs = {
            "model": model,
            "text": text,
            "ref_audio": ref_audio,
            "file_prefix": output_path.replace(".wav", ""),
        }
        
        # Add ref_text if provided (avoids transcription)
        if params.get("ref_text"):
            kwargs["ref_text"] = params.get("ref_text")
            
        # Generate audio
        generate_audio(**kwargs)
        
        # Find the generated file (mlx-audio uses _000 suffix)
        import glob
        base = output_path.replace(".wav", "")
        matches = glob.glob(f"{base}_*.wav")
        if matches:
            os.rename(matches[0], output_path)
            
        if not os.path.exists(output_path):
            raise Exception("Output file was not created by the model")
        
        print(json.dumps({"status": "completed", "output": output_path}), flush=True)
        
    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
