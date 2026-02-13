"""
Dual-Environment TTS Engine

Supports two TTS models using separate virtual environments:
- Qwen3-TTS: uses mlx-audio (venv_qwen3)
- CosyVoice3: uses mlx-audio-plus (venv_cosyvoice3)

Models are invoked via subprocess to ensure memory isolation.
"""
import os
import subprocess
import hashlib
import gc
import json
import tempfile
import numpy as np
import soundfile as sf
import re
import sys


class SubprocessTTSEngine:
    """
    TTS Engine that uses subprocess to call model-specific scripts
    in their respective virtual environments.
    """
    
    MODELS = {
        "qwen3": {
            "python": "./venv_qwen3/bin/python",
            "script": "core/tts_qwen3.py",
            "model_id": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16"
        },
        "cosyvoice3": {
            "python": "./venv_cosyvoice3/bin/python",
            "script": "core/tts_cosyvoice3.py",
            "model_id": "mlx-community/Fun-CosyVoice3-0.5B-2512-fp16"
        }
    }
    
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
        if model_type not in self.MODELS:
            raise ValueError(f"Unknown model type: {model_type}. Available: {list(self.MODELS.keys())}")
        self.model_type = model_type
        print(f"Model type set to: {model_type}")
        
    def intelligent_split(self, text, max_chars=150):
        """
        Splits text into chunks to avoid OOM or model degradation on long sequences.
        """
        sentences = re.split(r'([。！？\n.!?])', text)
        chunks = []
        current_chunk = ""
        
        for part in sentences:
            if len(current_chunk) + len(part) <= max_chars:
                current_chunk += part
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = part
        
        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks
    
    def transcribe_audio(self, audio_path):
        """Transcribe audio using CosyVoice3 environment to get reference text."""
        if not audio_path or not os.path.exists(audio_path):
            return ""
            
        # Check cache
        if audio_path in self._transcription_cache:
            print(f"Using cached transcription for: {audio_path}")
            return self._transcription_cache[audio_path]
            
        print(f"Transcribing reference audio: {audio_path}")
        
        # Always use CosyVoice3 environment for transcription
        config = self.MODELS["cosyvoice3"]
        python_exec = self._get_python_executable(config["python"])
        cmd = [python_exec, "core/transcribe.py", json.dumps({"audio_path": audio_path})]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            
            if result.returncode != 0:
                print(f"Transcription failed: {result.stderr}", file=sys.stderr)
                return ""
            
            for line in result.stdout.strip().split('\n'):
                if line:
                    try:
                        data = json.loads(line)
                        if data.get("status") == "completed":
                            text = data.get("text", "")
                            if text:
                                self._transcription_cache[audio_path] = text
                            return text
                    except:
                        pass
        except Exception as e:
            print(f"Transcription error: {e}", file=sys.stderr)
            
        return ""
    
    def generate_audio_chunk(self, text, ref_audio_path=None, output_path=None, ref_text=None):
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
            "model_id": config["model_id"]
        }
        
        python_exec = self._get_python_executable(config["python"])
        cmd = [python_exec, config["script"], json.dumps(params)]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout per chunk
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            
            # DEBUG: Print stderr/stdout to server log to see what's happening
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
    
    def generate_stream(self, text, ref_audio_path=None, speed=1.0):
        """
        Generator that yields (progress_percentage, audio_numpy_array)
        Compatible with existing app.py interface.
        """
        chunks = self.intelligent_split(text)
        total_chunks = len(chunks)
        
        ref_text = None
        # Use transcribe.py for ALL models to ensure consistent, high-quality reference text
        # and avoid internal auto-transcription issues
        if ref_audio_path:
            ref_text = self.transcribe_audio(ref_audio_path)
            if ref_text:
                print(f"Obtained reference text: {ref_text}")
        
        for i, chunk in enumerate(chunks):
            chunk = chunk.strip()
            chunk = chunk.replace('\n', ', ') # Replace inner newlines with commas
            if not chunk:
                continue
            
            # Mac Optimization: Aggressive Garbage Collection
            if i > 0 and i % 5 == 0:
                print("Running explicit GC for Mac optimization...")
                gc.collect()
            
            try:
                # Generate audio via subprocess
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    temp_path = f.name
                
                output_path = self.generate_audio_chunk(chunk, ref_audio_path, temp_path, ref_text=ref_text)
                
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
                
                # CRITICAL FIX: Do not continue silently. Raise error to stop task and notify user.
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
