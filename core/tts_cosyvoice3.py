#!/usr/bin/env python3
"""
CosyVoice3 Worker Script
Uses mlx-audio-plus to generate audio from text.
Called via subprocess from the main app.
"""
import sys
import json
import os

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: tts_cosyvoice3.py <json_params>"}))
        sys.exit(1)
    
    try:
        params = json.loads(sys.argv[1])
        text = params.get("text", "")
        ref_audio = params.get("ref_audio")
        ref_text = params.get("ref_text", "")
        output_path = params.get("output_path", "output.wav")
        model_id = params.get("model_id", "mlx-community/Fun-CosyVoice3-0.5B-2512-fp16")
        
        from mlx_audio.tts.generate import generate_audio
        
        print(json.dumps({"status": "loading", "message": "Loading CosyVoice3 model..."}), flush=True)
        
        print(json.dumps({"status": "generating", "message": f"Generating audio for: {text[:50]}..."}), flush=True)
        
        # Generate audio using CosyVoice3
        # Cross-lingual mode (default) or Zero-shot if ref_text provided
        kwargs = {
            "text": text,
            "model": model_id,
            "ref_audio": ref_audio,
            "file_prefix": output_path.replace(".wav", ""),
        }
        
        if ref_text:
            kwargs["ref_text"] = ref_text
        
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
        import traceback
        print(json.dumps({"status": "error", "error": str(e), "traceback": traceback.format_exc()}), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
