#!/usr/bin/env python3
"""
Qwen3-TTS Worker Script (v0.3.0)
Uses mlx-audio to generate audio from text.
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
        print(json.dumps({"error": "Usage: tts_qwen3.py <json_params>"}))
        sys.exit(1)

    try:
        params = json.loads(sys.argv[1])
        text = params.get("text", "")
        ref_audio = params.get("ref_audio")
        output_path = params.get("output_path", "output.wav")
        model_id = params.get("model_id", "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16")
        seed = params.get("seed", 42)

        # Set seed for reproducibility
        set_seed(seed)

        from mlx_audio.tts.generate import generate_audio
        from mlx_audio.tts.utils import load_model

        print(json.dumps({"status": "loading", "message": "Loading Qwen3-TTS model..."}), flush=True)
        model = load_model(model_id)

        print(json.dumps({"status": "generating", "message": f"Generating audio for: {text[:50]}..."}), flush=True)

        # Prepare args
        kwargs = {
            "model": model,
            "text": text,
            "file_prefix": output_path.replace(".wav", ""),
        }

        # ref_text is REQUIRED when using ref_audio with Qwen3,
        # because mlx_audio's internal Whisper transcription crashes
        # with "Processor not found" if ref_text is not provided.
        ref_text = params.get("ref_text", "")
        if ref_audio and ref_text:
            kwargs["ref_audio"] = ref_audio
            kwargs["ref_text"] = ref_text
            print(json.dumps({"status": "info", "message": "Using voice cloning (ref_audio + ref_text)"}), flush=True)
        elif ref_audio:
            # ref_audio without ref_text: skip voice cloning to avoid crash
            print(json.dumps({"status": "warning", "message": "ref_text missing, generating without voice cloning"}), flush=True)

        # Generate audio with fallback
        try:
            generate_audio(**kwargs)
        except Exception as gen_err:
            # If voice cloning failed, retry without ref_audio
            if "ref_audio" in kwargs:
                print(json.dumps({"status": "warning", "message": f"Voice cloning failed ({gen_err}), retrying without ref_audio..."}), flush=True)
                kwargs.pop("ref_audio", None)
                kwargs.pop("ref_text", None)
                generate_audio(**kwargs)
            else:
                raise

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
        print(json.dumps({"status": "error", "error": str(e)}), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
