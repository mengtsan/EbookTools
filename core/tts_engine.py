"""
Dual-Environment TTS Engine (v0.3.0)

Supports two TTS models using separate virtual environments:
- Qwen3-TTS: uses mlx-audio (venv_qwen3)
- CosyVoice3: uses mlx-audio-plus (venv_cosyvoice3)

Models are invoked via subprocess to ensure memory isolation.

Key v0.3.0 improvements:
- Smart 3-tier text splitting (TextSlicer)
- Per-chunk WAV caching for fault tolerance (crash-resume)
- GC + MPS cache cleanup for M4 optimization
- Fixed seed for consistent voice tone
- ffmpeg-based audio merging (AudioMerger)
"""
import os
import subprocess
import gc
import json
import tempfile
import numpy as np
import soundfile as sf
import re
import sys

from core.text_slicer import TextSlicer
from core.audio_merger import AudioMerger


class SubprocessTTSEngine:
    """
    TTS Engine that uses subprocess to call model-specific scripts
    in their respective virtual environments.
    """

    MODELS = {
        "qwen3": {
            "python": "./venv_qwen3/bin/python",
            "script": "core/tts_qwen3.py",
            "model_id": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
            "max_chars": 500,  # Qwen3 handles longer sequences
        },
        "cosyvoice3": {
            "python": "./venv_cosyvoice3/bin/python",
            "script": "core/tts_cosyvoice3.py",
            "model_id": "mlx-community/Fun-CosyVoice3-0.5B-2512-fp16",
            "max_chars": 300,  # CosyVoice3 needs shorter chunks
        }
    }

    # Default seed for reproducible voice tone
    DEFAULT_SEED = 42

    # GC interval: run garbage collection every N chunks
    GC_INTERVAL = 10

    def _get_python_executable(self, config_python):
        """
        Resolve python executable.
        If the configured path exists, use it.
        Otherwise, fallback to the current sys.executable (for portable/single-venv mode).
        """
        if os.path.exists(config_python):
            return config_python

        # Fallback to current python (assuming running in a venv that has dependencies)
        return sys.executable

    def __init__(self, model_type="qwen3"):
        self.model_type = model_type
        self._transcription_cache = {}

    def set_model_type(self, model_type):
        """Switch model type. Memory is automatically released since we use subprocess."""
        print(f"TRACE: set_model_type called with {model_type}", flush=True)
        if model_type not in self.MODELS:
            raise ValueError(f"Unknown model type: {model_type}. Available: {list(self.MODELS.keys())}")
        self.model_type = model_type
        print(f"Model type set to: {model_type}", flush=True)

    def get_text_slicer(self) -> TextSlicer:
        """Get a TextSlicer configured for the current model type."""
        max_chars = self.MODELS[self.model_type]["max_chars"]
        return TextSlicer(max_chars=max_chars)

    def transcribe_audio(self, audio_path):
        """Transcribe audio using available environments to get reference text.
        Tries CosyVoice3 env first, then falls back to other available venvs."""
        if not audio_path or not os.path.exists(audio_path):
            return ""

        # Check cache
        if audio_path in self._transcription_cache:
            print(f"Using cached transcription for: {audio_path}")
            return self._transcription_cache[audio_path]

        print(f"Transcribing reference audio: {audio_path}")

        # Try each environment in order (cosyvoice3 first, then qwen3)
        envs_to_try = ["cosyvoice3", "qwen3"]
        
        for env_name in envs_to_try:
            config = self.MODELS[env_name]
            python_exec = self._get_python_executable(config["python"])
            
            if not os.path.exists(python_exec):
                continue
                
            cmd = [python_exec, "core/transcribe.py", json.dumps({"audio_path": audio_path})]

            try:
                # Force unbuffered IO
                env = os.environ.copy()
                env["PYTHONUNBUFFERED"] = "1"
                
                print(f"DEBUG: Transcribing with command: {' '.join(cmd)}")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,  # 2 minute timeout for transcription
                    cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    env=env
                )
                
                # DEBUG: Log output
                # result.stdout and result.stderr are populated because capture_output=True
                # print(f"--- Transcribe Output ({env_name}) ---\n{result.stdout}\n--- kw ---") 


                if result.returncode != 0:
                    print(f"  Transcription failed with {env_name}: {result.stderr[:200]}", file=sys.stderr)
                    continue

                for line in result.stdout.strip().split('\n'):
                    if line:
                        try:
                            data = json.loads(line)
                            if data.get("status") == "completed":
                                text = data.get("text", "")
                                if text:
                                    self._transcription_cache[audio_path] = text
                                    print(f"  Transcription successful via {env_name}: {text[:50]}...")
                                    return text
                            elif data.get("status") == "error":
                                print(f"  Transcription error in {env_name}: {data.get('error', '')[:200]}", file=sys.stderr)
                        except json.JSONDecodeError:
                            pass
                            
            except subprocess.TimeoutExpired:
                print(f"  Transcription timed out with {env_name}", file=sys.stderr)
            except Exception as e:
                print(f"  Transcription error with {env_name}: {e}", file=sys.stderr)

        print("WARNING: All transcription attempts failed. Voice cloning may not work.", file=sys.stderr)
        return ""

    def _run_gc(self, chunk_index: int):
        """
        M4 optimization: Run garbage collection and clear MPS cache
        every GC_INTERVAL chunks to prevent memory bloat.
        """
        if chunk_index > 0 and chunk_index % self.GC_INTERVAL == 0:
            print(f"Running GC at chunk {chunk_index} (M4 memory optimization)...")
            gc.collect()
            try:
                import torch
                if hasattr(torch, 'mps') and hasattr(torch.mps, 'empty_cache'):
                    torch.mps.empty_cache()
                    print("Cleared MPS cache.")
            except ImportError:
                pass  # torch not available in main venv, that's fine

    def generate_audio_chunk(self, text, ref_audio_path=None, output_path=None,
                             ref_text=None, seed=None):
        """
        Generate audio for a single chunk of text using subprocess.
        Returns the path to the generated audio file.
        """
        config = self.MODELS[self.model_type]

        if output_path is None:
            output_path = tempfile.mktemp(suffix=".wav")

        params = {
            "text": text,
            "ref_audio": ref_audio_path,
            "ref_text": ref_text,
            "output_path": output_path,
            "model_id": config["model_id"],
            "seed": seed if seed is not None else self.DEFAULT_SEED,
        }

        python_exec = self._get_python_executable(config["python"])
        cmd = [python_exec, config["script"], json.dumps(params)]

        # Force unbuffered IO for subprocess to avoid hangs
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        try:
            print(f"DEBUG: Executing subprocess: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout per chunk
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                env=env
            )

            # DEBUG: Print stderr/stdout to server log
            print(f"--- Subprocess Output ({config['script']}) ---")
            print(result.stdout)
            print("--- Subprocess Stderr ---")
            print(result.stderr)
            print("---------------------------------------------")

            # Parse output lines for status updates
            for line in result.stdout.strip().split('\n'):
                if line:
                    try:
                        status = json.loads(line)
                        if isinstance(status, dict):
                            if status.get("status") == "error":
                                raise Exception(status.get("error", "Unknown error"))
                    except json.JSONDecodeError:
                        pass  # Non-JSON output, ignore

            if result.returncode != 0:
                raise Exception(f"Subprocess failed: {result.stderr}")

            if os.path.exists(output_path):
                # Verify file integrity
                try:
                    if os.path.getsize(output_path) < 100:
                        raise Exception(f"Output file too small: {os.path.getsize(output_path)} bytes")
                    # Try opening with soundfile
                    sf.info(output_path)
                    return output_path
                except Exception as e:
                    # Log subprocess output for debugging
                    logs = f"Stdout: {result.stdout}\nStderr: {result.stderr}"
                    print(logs, file=sys.stderr)
                    raise Exception(f"Generated file corrupted: {e}\nWorker Logs:\n{logs}")
            else:
                raise Exception(f"Output file not created: {output_path}")

        except subprocess.TimeoutExpired:
            raise Exception("Audio generation timed out")

    def generate_chapter(self, text, ref_audio_path=None,
                         chunk_dir=None, progress_callback=None):
        """
        Generate audio for an entire chapter with fault tolerance.

        This is the new primary generation method that:
        - Uses TextSlicer for smart splitting
        - Saves each chunk as chunk_XXXX.wav for crash-resume
        - Skips already-generated chunks (fault tolerance)
        - Runs GC/MPS cleanup periodically

        Args:
            text: Full chapter text
            ref_audio_path: Optional reference audio for voice cloning
            chunk_dir: Directory to save chunk WAVs (created if needed)
            progress_callback: Optional callable(chunk_idx, total_chunks, chunk_text)

        Returns:
            chunk_dir path containing all generated chunk_XXXX.wav files
        """
        slicer = self.get_text_slicer()
        chunks = slicer.slice(text)
        total_chunks = len(chunks)

        if total_chunks == 0:
            raise ValueError("No text chunks after slicing — chapter may be empty or all noise")

        # Create chunk directory if not provided
        if chunk_dir is None:
            chunk_dir = tempfile.mkdtemp(prefix="tts_chunks_")
        os.makedirs(chunk_dir, exist_ok=True)

        # Get reference text once (reused for all chunks)
        ref_text = None
        if ref_audio_path:
            ref_text = self.transcribe_audio(ref_audio_path)
            if ref_text:
                print(f"Obtained reference text: {ref_text}")

        print(f"Generating {total_chunks} chunks (model={self.model_type}, "
              f"max_chars={slicer.max_chars})")

        for i, chunk in enumerate(chunks):
            chunk = chunk.strip()
            chunk = chunk.replace('\n', '，')  # Replace inner newlines with comma
            if not chunk:
                continue

            chunk_path = os.path.join(chunk_dir, f"chunk_{i:04d}.wav")

            # Fault tolerance: skip if chunk already exists and is valid
            if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 100:
                try:
                    sf.info(chunk_path)
                    print(f"  Chunk {i+1}/{total_chunks}: SKIP (already exists)")
                    if progress_callback:
                        progress_callback(i, total_chunks, chunk)
                    continue
                except Exception:
                    # File exists but is corrupted, regenerate
                    os.remove(chunk_path)

            print(f"  Chunk {i+1}/{total_chunks}: \"{chunk[:40]}...\"")

            # Generate
            self.generate_audio_chunk(
                chunk, ref_audio_path, chunk_path,
                ref_text=ref_text, seed=self.DEFAULT_SEED
            )

            # Report progress
            if progress_callback:
                progress_callback(i, total_chunks, chunk)

            # M4 optimization: periodic GC
            self._run_gc(i)

        print(f"All {total_chunks} chunks generated in {chunk_dir}")
        return chunk_dir

    def generate_stream(self, text, ref_audio_path=None, speed=1.0):
        """
        Generator that yields (progress_percentage, audio_numpy_array)
        Compatible with existing app.py interface.

        NOTE: This is the legacy interface. New code should use
        generate_chapter() + AudioMerger for better fault tolerance.
        """
        slicer = self.get_text_slicer()
        chunks = slicer.slice(text)
        total_chunks = len(chunks)

        ref_text = None
        if ref_audio_path:
            ref_text = self.transcribe_audio(ref_audio_path)
            if ref_text:
                print(f"Obtained reference text: {ref_text}")

        for i, chunk in enumerate(chunks):
            chunk = chunk.strip()
            chunk = chunk.replace('\n', '，')
            if not chunk:
                continue

            # M4 Optimization: Aggressive Garbage Collection
            self._run_gc(i)

            try:
                # Generate audio via subprocess
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    temp_path = f.name

                output_path = self.generate_audio_chunk(
                    chunk, ref_audio_path, temp_path,
                    ref_text=ref_text, seed=self.DEFAULT_SEED
                )

                # Load and yield the audio
                if output_path and os.path.exists(output_path):
                    audio, sr = sf.read(output_path)
                    yield (i + 1) / total_chunks, audio

                    # Cleanup temp file
                    try:
                        os.remove(output_path)
                    except:
                        pass

            except Exception as e:
                error_msg = f"Error generating chunk {i}: {e}"
                print(error_msg, file=sys.stderr)
                import traceback
                tb = traceback.format_exc()
                print(tb, file=sys.stderr)
                # Also write to error log
                try:
                    with open("chunk_error.log", "a") as f:
                        f.write(f"\n=== Chunk {i} Error ===\n{error_msg}\n{tb}\n")
                except:
                    pass

                # CRITICAL: Raise to stop and notify user
                raise Exception(f"Chunk generation failed: {e}")


# Create global instance for backward compatibility
tts_engine = SubprocessTTSEngine()


# Legacy MLXEngine class for compatibility (deprecated)
class MLXEngine:
    """Deprecated. Use SubprocessTTSEngine instead."""

    def __init__(self, model_id="mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"):
        self._subprocess_engine = SubprocessTTSEngine()
        if "cosyvoice" in model_id.lower():
            self._subprocess_engine.set_model_type("cosyvoice3")
        else:
            self._subprocess_engine.set_model_type("qwen3")

    def load_model_by_type(self, model_type):
        self._subprocess_engine.set_model_type(model_type)

    def load(self):
        pass  # No-op: subprocess loads on demand

    def generate_stream(self, text, ref_audio_path=None, speed=1.0):
        return self._subprocess_engine.generate_stream(text, ref_audio_path, speed)
