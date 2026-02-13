#!/usr/bin/env python3
"""
Test suite for TextSlicer — can run without TTS models.
"""
import sys
sys.path.insert(0, '.')
from core.text_slicer import TextSlicer


def test_basic_split():
    """Test basic paragraph splitting."""
    slicer = TextSlicer(max_chars=300)
    text = "第一段落的長文字內容要超過十個字。\n第二段落的長文字內容要超過十個字。\n第三段落的長文字內容也要超過十個字。"
    chunks = slicer.slice(text)
    assert len(chunks) == 3, f"Expected 3 chunks, got {len(chunks)}: {chunks}"
    print("✅ test_basic_split passed")


def test_short_merge():
    """Short lines (< 10 chars) should merge into previous."""
    slicer = TextSlicer(max_chars=300)
    text = "這是一段正常長度的文字內容，超過十個字。\n短\n另一段正常長度的文字內容也超過十個字。"
    chunks = slicer.slice(text)
    # "短" (1 char) should merge into previous
    assert len(chunks) == 2, f"Expected 2 chunks (short merged), got {len(chunks)}: {chunks}"
    assert "短" in chunks[0], f"Short text should be merged into first chunk: {chunks}"
    print("✅ test_short_merge passed")


def test_long_split():
    """Long lines (> max_chars) should split at punctuation."""
    slicer = TextSlicer(max_chars=50)
    text = "這是一段很長的文字。它包含多個句子。每個句子都有標點符號。這樣就可以在標點處切分。確保不會超過最大長度限制。"
    chunks = slicer.slice(text)
    for chunk in chunks:
        assert len(chunk) <= 50, f"Chunk too long ({len(chunk)} chars): {chunk}"
    assert len(chunks) > 1, "Should split into multiple chunks"
    print(f"✅ test_long_split passed ({len(chunks)} chunks)")


def test_noise_cleaning():
    """Markdown noise characters should be removed."""
    slicer = TextSlicer(max_chars=300)
    text = "# 標題\n\n正常文字內容。\n\n---\n\n**加粗文字**\n\n> 引用文字"
    chunks = slicer.slice(text)
    for chunk in chunks:
        assert '#' not in chunk, f"# should be cleaned: {chunk}"
        assert '---' not in chunk, f"--- should be cleaned: {chunk}"
        assert '**' not in chunk, f"** should be cleaned: {chunk}"
    print(f"✅ test_noise_cleaning passed ({len(chunks)} chunks)")


def test_empty_input():
    """Empty or whitespace-only input should return empty list."""
    slicer = TextSlicer(max_chars=300)
    assert slicer.slice("") == [], "Empty string should return []"
    assert slicer.slice("   ") == [], "Whitespace-only should return []"
    assert slicer.slice("\n\n\n") == [], "Newlines-only should return []"
    print("✅ test_empty_input passed")


def test_mixed_language():
    """Mixed Chinese + English text should work."""
    slicer = TextSlicer(max_chars=300)
    text = "Hello World，你好世界！\nThis is a test.\n這是測試。"
    chunks = slicer.slice(text)
    assert len(chunks) >= 2, f"Expected >= 2 chunks, got {len(chunks)}: {chunks}"
    print(f"✅ test_mixed_language passed ({len(chunks)} chunks)")


def test_model_specific_defaults():
    """Test CosyVoice (300) vs Qwen3 (500) defaults."""
    cosy_slicer = TextSlicer(max_chars=300)
    qwen_slicer = TextSlicer(max_chars=500)
    
    # Create a 400-char text
    text = "這是一段很長的文字。" * 40  # ~200 chars
    
    cosy_chunks = cosy_slicer.slice(text)
    qwen_chunks = qwen_slicer.slice(text)
    
    # Qwen should produce fewer chunks since it allows longer ones
    assert len(cosy_chunks) >= len(qwen_chunks), \
        f"CosyVoice ({len(cosy_chunks)} chunks) should produce >= Qwen ({len(qwen_chunks)} chunks)"
    print(f"✅ test_model_specific_defaults passed (cosy={len(cosy_chunks)}, qwen={len(qwen_chunks)})")


def test_all_short_lines():
    """Multiple short lines should all merge into one."""
    slicer = TextSlicer(max_chars=300)
    text = "一\n二\n三\n四\n五"
    chunks = slicer.slice(text)
    assert len(chunks) == 1, f"Expected 1 merged chunk, got {len(chunks)}: {chunks}"
    print(f"✅ test_all_short_lines passed: {chunks}")


if __name__ == "__main__":
    print("=== TextSlicer Tests ===\n")
    test_basic_split()
    test_short_merge()
    test_long_split()
    test_noise_cleaning()
    test_empty_input()
    test_mixed_language()
    test_model_specific_defaults()
    test_all_short_lines()
    print("\n🎉 All tests passed!")
