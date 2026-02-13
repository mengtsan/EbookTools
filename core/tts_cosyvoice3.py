#!/usr/bin/env python3
"""
CosyVoice3 Worker Script (v0.3.0)
Uses mlx-audio-plus to generate audio from text.
Called via subprocess from the main app.

v0.3.0: Added seed control and silence padding.
"""
import sys
import json
import os
import random
import numpy as np


def set_seed(seed):
    """Set random seed for reproducible voice tone."""
    random.seed(seed)
    np.random.seed(seed)
    try:
        import mlx.core as mx
        mx.random.seed(seed)
    except ImportError:
        pass


def add_silence_padding(audio_path, pad_ms=200, sample_rate=24000):
    """
    Add silence padding before and after the audio file.
    This prevents chunks from sounding too abrupt when concatenated.
    """
    import soundfile as sf

    audio, sr = sf.read(audio_path)

    # Generate silence samples
    pad_samples = int(sample_rate * pad_ms / 1000)
    silence = np.zeros(pad_samples, dtype=audio.dtype)

    # Concatenate: silence + audio + silence
    padded = np.concatenate([silence, audio, silence])

    sf.write(audio_path, padded, sr)


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
        seed = params.get("seed", 42)

        # Set seed for reproducibility
        set_seed(seed)

        from mlx_audio.tts.generate import generate_audio

        print(json.dumps({"status": "loading", "message": "Loading CosyVoice3 model..."}), flush=True)

        print(json.dumps({"status": "generating", "message": f"Generating audio for: {text[:50]}..."}), flush=True)

        # Generate audio using CosyVoice3
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

        # Add silence padding for natural pacing when concatenated
        add_silence_padding(output_path, pad_ms=200)

        print(json.dumps({"status": "completed", "output": output_path}), flush=True)

    except Exception as e:
        import traceback
        print(json.dumps({"status": "error", "error": str(e), "traceback": traceback.format_exc()}), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
