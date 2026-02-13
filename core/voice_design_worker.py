import sys
import os
import json
import uuid
import soundfile as sf
import numpy as np

# Ensure we can import from local if needed, though usually standard imports suffice
# But we need mlx_audio here.

try:
    import mlx.core as mx
    from mlx_audio.tts.utils import load_model, base_load_model, get_model_class
    from mlx_audio.tts.generate import generate_audio
except ImportError as e:
    print(json.dumps({"status": "error", "error": f"ImportError: {e}"}))
    sys.exit(1)

def generate_voice_design(text, instruct, language, output_path, model_id):
    print(json.dumps({"status": "loading", "message": f"Loading model {model_id}..."}), flush=True)
    
    try:
        # Load model
        # Using mlx_audio load_model
        model = load_model(model_id)
        
        print(json.dumps({"status": "generating", "message": "Generating audio..."}), flush=True)
        
        # Check if model supports generate_voice_design
        if hasattr(model, "generate_voice_design"):
            results = list(model.generate_voice_design(
                text=text,
                language=language,
                instruct=instruct
            ))
            
            if not results:
                raise ValueError("No audio generated.")
                
            all_audio = []
            sr = 24000
            for res in results:
                if res.audio is not None:
                    if isinstance(res.audio, mx.array):
                        all_audio.append(np.array(res.audio))
                    elif isinstance(res.audio, np.ndarray):
                        all_audio.append(res.audio)
                    sr = res.sample_rate
            
            if not all_audio:
                 raise ValueError("Generated results contain no audio data.")

            audio_data = np.concatenate(all_audio)
            
            sf.write(output_path, audio_data, sr)
            
            print(json.dumps({"status": "success", "output_path": output_path}), flush=True)
            
        else:
             raise NotImplementedError("Model does not support generate_voice_design method.")

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(json.dumps({"status": "error", "error": str(e), "traceback": tb}), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python voice_design_worker.py <input_json>"}), flush=True)
        sys.exit(1)
        
    input_file = sys.argv[1]
    
    try:
        with open(input_file, 'r') as f:
            data = json.load(f)
            
        text = data.get("text")
        instruct = data.get("instruct")
        language = data.get("language", "Chinese")
        output_path = data.get("output_path")
        model_id = data.get("model_id", "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16")
        
        generate_voice_design(text, instruct, language, output_path, model_id)
        
    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}), flush=True)
        sys.exit(1)
