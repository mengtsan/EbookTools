import sys
import os

print(f"Checking environment: {sys.executable}")
print(f"Python version: {sys.version}")

try:
    import scipy
    print(f"✅ Scipy found: {scipy.__file__}")
    from scipy.signal import resample
    print("✅ Scipy signal.resample importable")
except ImportError as e:
    print(f"❌ Scipy import failed: {e}")
    sys.exit(1)

try:
    import mlx_audio
    print(f"✅ mlx_audio found: {mlx_audio.__file__}")
    # Check CosyVoice3 model directory exists
    import os
    models_dir = os.path.join(os.path.dirname(mlx_audio.__file__), "tts", "models", "cosyvoice3")
    if os.path.isdir(models_dir):
        print(f"✅ CosyVoice3 model directory found: {models_dir}")
    else:
        print(f"❌ CosyVoice3 model directory MISSING: {models_dir}")
        print("   mlx-audio may need --force-reinstall --no-cache-dir")
        sys.exit(1)
except ImportError as e:
    print(f"❌ mlx_audio import failed: {e}")
    sys.exit(1)

try:
    import sounddevice
    print(f"✅ sounddevice found: {sounddevice.__file__}")
except ImportError as e:
    print(f"❌ sounddevice import failed: {e}")
    sys.exit(1)

try:
    import mlx_lm
    print(f"✅ mlx-lm found: {mlx_lm.__file__}")
except ImportError as e:
    print(f"❌ mlx-lm import failed: {e}")
    sys.exit(1)

try:
    import mlx_whisper
    print(f"✅ mlx-whisper found: {mlx_whisper.__file__}")
except ImportError as e:
    print(f"❌ mlx-whisper import failed: {e}")
    sys.exit(1)

print("Environment verification successful!")
