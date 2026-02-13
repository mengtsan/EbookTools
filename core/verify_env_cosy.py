import sys
import os

print(f"Checking environment: {sys.executable}")
print(f"Python version: {sys.version}")

errors = []

# --- scipy ---
try:
    import scipy
    from scipy.signal import resample
    print(f"✅ scipy {scipy.__version__}")
except ImportError as e:
    print(f"❌ scipy: {e}")
    errors.append("scipy")

# --- mlx_audio + cosyvoice3 model ---
try:
    import mlx_audio
    print(f"✅ mlx-audio {mlx_audio.__version__ if hasattr(mlx_audio, '__version__') else 'ok'}")
    models_dir = os.path.join(os.path.dirname(mlx_audio.__file__), "tts", "models", "cosyvoice3")
    if os.path.isdir(models_dir):
        print(f"✅ cosyvoice3 model directory found")
    else:
        print(f"❌ cosyvoice3 model directory MISSING")
        print("   需要安裝: pip install --no-deps mlx-audio-plus==0.1.8")
        errors.append("cosyvoice3-model")
except ImportError as e:
    print(f"❌ mlx-audio: {e}")
    errors.append("mlx-audio")

# --- sounddevice ---
try:
    import sounddevice
    print(f"✅ sounddevice {sounddevice.__version__}")
except ImportError as e:
    print(f"❌ sounddevice: {e}")
    errors.append("sounddevice")

# --- mlx-lm ---
try:
    import mlx_lm
    print(f"✅ mlx-lm ok")
except ImportError as e:
    print(f"❌ mlx-lm: {e}")
    errors.append("mlx-lm")

# --- mlx-whisper ---
try:
    import mlx_whisper
    print(f"✅ mlx-whisper ok")
except ImportError as e:
    print(f"❌ mlx-whisper: {e}")
    errors.append("mlx-whisper")

# --- einops ---
try:
    import einops
    print(f"✅ einops {einops.__version__}")
except ImportError as e:
    print(f"❌ einops: {e}")
    errors.append("einops")

# --- Result ---
if errors:
    print(f"\n❌ {len(errors)} package(s) missing: {', '.join(errors)}")
    sys.exit(1)
else:
    print("\n✅ Environment verification successful!")

