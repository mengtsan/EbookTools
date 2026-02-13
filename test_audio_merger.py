#!/usr/bin/env python3
"""
Test suite for AudioMerger — requires ffmpeg installed.
Generates short WAV files and tests merge functionality.
"""
import sys
import os
import tempfile
import shutil
import numpy as np
import struct

sys.path.insert(0, '.')
from core.audio_merger import AudioMerger


def create_test_wav(path, duration_s=0.5, sample_rate=24000, frequency=440):
    """Create a simple sine wave WAV file for testing."""
    num_samples = int(sample_rate * duration_s)
    t = np.linspace(0, duration_s, num_samples, endpoint=False)
    audio = (np.sin(2 * np.pi * frequency * t) * 0.5 * 32767).astype(np.int16)
    
    # Write WAV file manually (no external deps needed)
    with open(path, 'wb') as f:
        # RIFF header
        data_size = num_samples * 2  # 16-bit = 2 bytes per sample
        f.write(b'RIFF')
        f.write(struct.pack('<I', 36 + data_size))
        f.write(b'WAVE')
        # fmt chunk
        f.write(b'fmt ')
        f.write(struct.pack('<I', 16))      # chunk size
        f.write(struct.pack('<H', 1))       # PCM
        f.write(struct.pack('<H', 1))       # mono
        f.write(struct.pack('<I', sample_rate))
        f.write(struct.pack('<I', sample_rate * 2))  # byte rate
        f.write(struct.pack('<H', 2))       # block align
        f.write(struct.pack('<H', 16))      # bits per sample
        # data chunk
        f.write(b'data')
        f.write(struct.pack('<I', data_size))
        f.write(audio.tobytes())


def test_merge_basic():
    """Test merging 3 WAV chunks into 1 MP3."""
    chunk_dir = tempfile.mkdtemp(prefix="test_merger_")
    output_path = os.path.join(chunk_dir, "output.mp3")
    
    try:
        # Create 3 test chunks
        for i in range(3):
            create_test_wav(
                os.path.join(chunk_dir, f"chunk_{i:04d}.wav"),
                duration_s=0.3,
                frequency=440 + i * 100
            )
        
        # Merge
        result = AudioMerger.merge_chunks(
            chunk_dir=chunk_dir,
            output_path=output_path,
            silence_ms=300,
            bitrate="192k"
        )
        
        assert os.path.exists(result), f"Output file not created: {result}"
        assert os.path.getsize(result) > 100, f"Output file too small: {os.path.getsize(result)}"
        print(f"✅ test_merge_basic passed (output: {os.path.getsize(result)} bytes)")
        
    finally:
        shutil.rmtree(chunk_dir, ignore_errors=True)


def test_merge_with_tags():
    """Test merging with MP3 metadata tags."""
    chunk_dir = tempfile.mkdtemp(prefix="test_merger_tags_")
    output_path = os.path.join(chunk_dir, "output.mp3")
    
    try:
        create_test_wav(os.path.join(chunk_dir, "chunk_0000.wav"), duration_s=0.5)
        
        result = AudioMerger.merge_chunks(
            chunk_dir=chunk_dir,
            output_path=output_path,
            tags={"title": "Test Chapter", "artist": "CosyVoice AI", "album": "Test Book"}
        )
        
        assert os.path.exists(result), "Output file not created"
        print(f"✅ test_merge_with_tags passed (output: {os.path.getsize(result)} bytes)")
        
    finally:
        shutil.rmtree(chunk_dir, ignore_errors=True)


def test_cleanup():
    """Test that cleanup removes the chunk directory."""
    chunk_dir = tempfile.mkdtemp(prefix="test_cleanup_")
    create_test_wav(os.path.join(chunk_dir, "chunk_0000.wav"))
    
    assert os.path.isdir(chunk_dir)
    AudioMerger.cleanup(chunk_dir)
    assert not os.path.isdir(chunk_dir), "Directory should be removed after cleanup"
    print("✅ test_cleanup passed")


def test_empty_dir():
    """Test that merging an empty directory raises FileNotFoundError."""
    chunk_dir = tempfile.mkdtemp(prefix="test_empty_")
    
    try:
        AudioMerger.merge_chunks(
            chunk_dir=chunk_dir,
            output_path=os.path.join(chunk_dir, "output.mp3")
        )
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError:
        print("✅ test_empty_dir passed (correctly raised FileNotFoundError)")
    finally:
        shutil.rmtree(chunk_dir, ignore_errors=True)


def test_sorted_order():
    """Test that chunks are merged in correct sorted order."""
    chunk_dir = tempfile.mkdtemp(prefix="test_order_")
    output_path = os.path.join(chunk_dir, "output.mp3")
    
    try:
        # Create chunks out of order
        for i in [2, 0, 1]:
            create_test_wav(
                os.path.join(chunk_dir, f"chunk_{i:04d}.wav"),
                duration_s=0.2,
                frequency=440 + i * 200
            )
        
        sorted_chunks = AudioMerger._get_sorted_chunks(chunk_dir)
        assert [os.path.basename(c) for c in sorted_chunks] == \
               ["chunk_0000.wav", "chunk_0001.wav", "chunk_0002.wav"], \
               f"Chunks not sorted correctly: {sorted_chunks}"
        
        result = AudioMerger.merge_chunks(chunk_dir, output_path)
        assert os.path.exists(result)
        print("✅ test_sorted_order passed")
        
    finally:
        shutil.rmtree(chunk_dir, ignore_errors=True)


if __name__ == "__main__":
    print("=== AudioMerger Tests ===\n")
    
    # Check ffmpeg availability first
    import subprocess
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True)
        if result.returncode != 0:
            print("❌ ffmpeg not found. Install with: brew install ffmpeg")
            sys.exit(1)
        print("ffmpeg found ✓\n")
    except FileNotFoundError:
        print("❌ ffmpeg not found. Install with: brew install ffmpeg")
        sys.exit(1)
    
    test_merge_basic()
    test_merge_with_tags()
    test_cleanup()
    test_empty_dir()
    test_sorted_order()
    print("\n🎉 All tests passed!")
