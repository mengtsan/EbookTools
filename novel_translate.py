#!/usr/bin/env python3
"""
Novel Translation Script for HY-MT1.5 (GGUF) on Apple Silicon
==============================================================
使用 llama-cpp-python 載入 HY-MT1.5 GGUF 模型，搭配：
  1. 術語注入 (Terminology Intervention) — 官方 Prompt 格式
  2. 滑動視窗 (Sliding Window) — 前段譯文作為上下文
  3. 文學性翻譯 — 台灣繁體中文小說筆法

依賴：llama-cpp-python, tqdm, huggingface_hub
硬體：Mac Mini M4 (32GB) with Metal GPU offload

Usage:
    python novel_translate.py --input novel.txt --glossary glossary.json --output translation_output.txt
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from tqdm import tqdm

# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────
DEFAULT_MODEL_REPO = "Mungert/Hunyuan-MT-7B-GGUF"
DEFAULT_MODEL_FILE = "Hunyuan-MT-7B-q8_0.gguf"
DEFAULT_N_CTX = 8192
DEFAULT_N_GPU_LAYERS = -1  # Full GPU offload (Metal)

# Chunking parameters
MIN_CHUNK_CHARS = 50       # Merge paragraphs shorter than this
MAX_CHUNK_CHARS = 800      # Split paragraphs longer than this
PREV_CONTEXT_CHARS = 200   # Characters of previous translation to include

# Generation parameters (official HY-MT1.5 recommendation)
GEN_PARAMS = {
    "top_k": 20,
    "top_p": 0.6,
    "repeat_penalty": 1.05,
    "temperature": 0.7,
}


# ──────────────────────────────────────────────
# 1. Model Download & Loading
# ──────────────────────────────────────────────
def download_model(repo_id: str, filename: str) -> str:
    """Download GGUF model from HuggingFace Hub. Returns local path."""
    from huggingface_hub import hf_hub_download

    print(f"📦 正在檢查/下載模型: {repo_id}/{filename}")
    print("   （首次執行需下載 ~8GB，請耐心等待）")
    local_path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        resume_download=True,
    )
    print(f"✅ 模型路徑: {local_path}")
    return local_path


def load_model(model_path: str, n_ctx: int = DEFAULT_N_CTX,
               n_gpu_layers: int = DEFAULT_N_GPU_LAYERS):
    """Load GGUF model with llama-cpp-python (Metal GPU offload)."""
    from llama_cpp import Llama

    print(f"🔧 正在載入模型 (n_ctx={n_ctx}, GPU layers={n_gpu_layers})...")
    t0 = time.time()

    llm = Llama(
        model_path=model_path,
        n_ctx=n_ctx,
        n_gpu_layers=n_gpu_layers,
        verbose=False,
        # Apple Silicon specific
        use_mmap=True,
        use_mlock=False,
    )

    elapsed = time.time() - t0
    print(f"✅ 模型載入完成 ({elapsed:.1f}s)")
    return llm


# ──────────────────────────────────────────────
# 2. Input Loading
# ──────────────────────────────────────────────
def load_source_text(filepath: str) -> str:
    """Load source novel text file."""
    path = Path(filepath)
    if not path.exists():
        print(f"❌ 找不到原文檔案: {filepath}")
        sys.exit(1)

    text = path.read_text(encoding="utf-8")
    print(f"📖 已載入原文: {path.name} ({len(text)} 字)")
    return text


def load_glossary(filepath: str) -> dict:
    """Load glossary JSON file (key-value pairs)."""
    path = Path(filepath)
    if not path.exists():
        print(f"⚠️  找不到術語表: {filepath}，將不使用術語注入")
        return {}

    with open(path, "r", encoding="utf-8") as f:
        glossary = json.load(f)

    print(f"📚 已載入術語表: {len(glossary)} 筆 ({', '.join(list(glossary.keys())[:5])}...)")
    return glossary


# ──────────────────────────────────────────────
# 3. Smart Chunking
# ──────────────────────────────────────────────
def smart_chunk(text: str, min_chars: int = MIN_CHUNK_CHARS,
                max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """
    Split source text into translation-friendly chunks.

    Strategy:
      1. Split by double newlines (paragraphs)
      2. Merge short paragraphs (< min_chars) into previous chunk
      3. Split long paragraphs (> max_chars) at sentence boundaries
    """
    # Step 1: Split into raw paragraphs
    raw_paragraphs = re.split(r'\n\s*\n', text.strip())
    raw_paragraphs = [p.strip() for p in raw_paragraphs if p.strip()]

    # If no double-newline splits, try single newlines
    if len(raw_paragraphs) <= 1 and len(text.strip()) > max_chars:
        raw_paragraphs = text.strip().split('\n')
        raw_paragraphs = [p.strip() for p in raw_paragraphs if p.strip()]

    # Step 2: Merge short paragraphs
    merged = []
    buffer = ""
    for para in raw_paragraphs:
        if buffer and len(buffer) + len(para) < min_chars:
            buffer += "\n" + para
        elif buffer and len(buffer) < min_chars:
            buffer += "\n" + para
        else:
            if buffer:
                merged.append(buffer)
            buffer = para
    if buffer:
        merged.append(buffer)

    # Step 3: Split long paragraphs at sentence boundaries
    chunks = []
    for para in merged:
        if len(para) <= max_chars:
            chunks.append(para)
        else:
            # Split at sentence-ending punctuation
            sentences = re.split(r'(?<=[。！？.!?"\"\n])\s*', para)
            current = ""
            for sent in sentences:
                if not sent.strip():
                    continue
                if len(current) + len(sent) > max_chars and current:
                    chunks.append(current.strip())
                    current = sent
                else:
                    current += (" " if current else "") + sent
            if current.strip():
                chunks.append(current.strip())

    # Final cleanup: remove empty chunks
    chunks = [c for c in chunks if c.strip()]
    return chunks


# ──────────────────────────────────────────────
# 4. Prompt Construction (The Secret Sauce)
# ──────────────────────────────────────────────
def build_glossary_string(glossary: dict) -> str:
    """
    Convert glossary to HY-MT1.5 terminology intervention format.

    Official format:
      參考下面的翻譯：
      {source_term} 翻譯成 {target_term}
    """
    if not glossary:
        return ""

    lines = []
    for src, tgt in glossary.items():
        lines.append(f"{src} 翻译成 {tgt}")

    return "参考下面的翻译：\n" + "\n".join(lines) + "\n"


def build_prompt(source_chunk: str, glossary: dict,
                 prev_translation: str = "", target_language: str = "繁體中文") -> str:
    """
    Construct the translation prompt combining:
      1. Terminology Intervention (official HY-MT1.5 format)
      2. Contextual Translation (sliding window of previous output)
      3. Literary style instructions

    The prompt follows HY-MT1.5's official contextual translation template:
      {context}
      參考上面的信息，把下面的文本翻譯成{target_language}，
      注意不需要翻譯上文，也不要額外解釋：
      {source_text}
    """
    parts = []

    # Part 1: Terminology injection
    glossary_str = build_glossary_string(glossary)
    if glossary_str:
        parts.append(glossary_str)

    # Part 2: Previous translation context (sliding window)
    if prev_translation:
        # Take last N chars of previous translation
        context_text = prev_translation[-PREV_CONTEXT_CHARS:]
        # Don't cut mid-sentence: find the first sentence boundary
        first_break = 0
        for i, ch in enumerate(context_text):
            if ch in "。！？\n":
                first_break = i + 1
                break
        if first_break > 0:
            context_text = context_text[first_break:]
        if context_text.strip():
            parts.append(context_text.strip())

    # Part 3: Translation instruction + source text
    context_block = "\n".join(parts)

    if context_block.strip():
        # Use contextual translation template
        # Official SC Template
        prompt = (
            f"{context_block}\n"
            f"参考上面的信息，把下面的文本翻译成{target_language}，"
            f"注意不需要翻译上文，也不要额外解释：\n"
            f"{source_chunk}"
        )
    else:
        # No context available (first chunk, no glossary)
        # Official SC Template
        prompt = (
            f"将以下文本翻译为{target_language}，注意只需要输出翻译后的结果，不要额外解释：\n"
            f"{source_chunk}"
        )

    return prompt


def format_for_chat(prompt: str) -> list[dict]:
    """
    Format prompt as chat messages for HY-MT1.5.
    Note: HY-MT1.5 does NOT use system prompt (per official docs).
    """
    return [{"role": "user", "content": prompt}]


# ──────────────────────────────────────────────
# 5. Translation Engine
# ──────────────────────────────────────────────
def translate_chunk(llm, source_chunk: str, glossary: dict,
                    prev_translation: str = "") -> str:
    """Translate a single chunk using the model."""
    prompt = build_prompt(source_chunk, glossary, prev_translation)
    messages = format_for_chat(prompt)

    response = llm.create_chat_completion(
        messages=messages,
        max_tokens=2048,
        **GEN_PARAMS,
    )

    # Extract the assistant's response
    result = response["choices"][0]["message"]["content"]
    return result.strip()


def translate_novel(llm, chunks: list[str], glossary: dict,
                    output_path: str) -> str:
    """
    Translate all chunks with sliding window context.
    Writes results to output file in real-time.
    """
    all_translations = []
    prev_translation = ""

    # Open output file for real-time writing
    out_path = Path(output_path)
    with open(out_path, "w", encoding="utf-8") as f_out:
        pbar = tqdm(chunks, desc="📝 翻譯中", unit="段",
                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")

        for i, chunk in enumerate(pbar):
            # Update progress bar description
            preview = chunk[:30].replace('\n', ' ')
            pbar.set_postfix_str(f"「{preview}...」")

            # Translate with context injection
            translated = translate_chunk(llm, chunk, glossary, prev_translation)

            # Write to file immediately
            f_out.write(translated)
            f_out.write("\n\n")
            f_out.flush()

            # Update sliding window
            all_translations.append(translated)
            prev_translation = translated

    full_translation = "\n\n".join(all_translations)
    return full_translation


# ──────────────────────────────────────────────
# 6. Main Entry Point
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="HY-MT1.5 小說翻譯腳本 (GGUF + Apple Silicon)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python novel_translate.py --input novel.txt
  python novel_translate.py --input novel.txt --glossary glossary.json
  python novel_translate.py --input novel.txt --glossary glossary.json --output my_translation.txt
  python novel_translate.py --input novel.txt --model-path /path/to/custom.gguf
        """,
    )

    parser.add_argument("--input", "-i", required=True,
                        help="原文小說文字檔路徑 (novel.txt)")
    parser.add_argument("--glossary", "-g", default="glossary.json",
                        help="術語表 JSON 檔路徑 (預設: glossary.json)")
    parser.add_argument("--output", "-o", default="translation_output.txt",
                        help="輸出譯文檔路徑 (預設: translation_output.txt)")
    parser.add_argument("--model-path", default=None,
                        help="GGUF 模型檔路徑 (不指定則自動下載)")
    parser.add_argument("--model-repo", default=DEFAULT_MODEL_REPO,
                        help=f"HuggingFace 模型 repo (預設: {DEFAULT_MODEL_REPO})")
    parser.add_argument("--model-file", default=DEFAULT_MODEL_FILE,
                        help=f"GGUF 檔名 (預設: {DEFAULT_MODEL_FILE})")
    parser.add_argument("--n-ctx", type=int, default=DEFAULT_N_CTX,
                        help=f"上下文視窗大小 (預設: {DEFAULT_N_CTX})")
    parser.add_argument("--n-gpu-layers", type=int, default=DEFAULT_N_GPU_LAYERS,
                        help="GPU offload 層數 (-1=全部, 預設: -1)")
    parser.add_argument("--max-chunk-chars", type=int, default=MAX_CHUNK_CHARS,
                        help=f"每段最大字數 (預設: {MAX_CHUNK_CHARS})")

    args = parser.parse_args()

    # Banner
    print("=" * 60)
    print("  📖 HY-MT1.5 小說翻譯腳本")
    print("  🍎 Apple Silicon (Metal) Optimized")
    print("  🔧 Powered by llama-cpp-python + GGUF")
    print("=" * 60)
    print()

    # Step 1: Load or download model
    if args.model_path:
        model_path = args.model_path
        if not Path(model_path).exists():
            print(f"❌ 指定的模型檔不存在: {model_path}")
            sys.exit(1)
    else:
        model_path = download_model(args.model_repo, args.model_file)

    # Step 2: Load model
    llm = load_model(model_path, n_ctx=args.n_ctx,
                     n_gpu_layers=args.n_gpu_layers)

    # Step 3: Load inputs
    source_text = load_source_text(args.input)
    glossary = load_glossary(args.glossary)

    # Step 4: Smart chunking
    print(f"\n✂️  正在進行智慧分段 (max_chars={args.max_chunk_chars})...")
    chunks = smart_chunk(source_text, max_chars=args.max_chunk_chars)
    print(f"   分為 {len(chunks)} 段")

    # Show chunk preview
    for i, c in enumerate(chunks[:3]):
        preview = c[:60].replace('\n', '↵')
        print(f"   [{i+1}] {preview}...")
    if len(chunks) > 3:
        print(f"   ... 共 {len(chunks)} 段")

    # Step 5: Translate
    print(f"\n🚀 開始翻譯 → {args.output}")
    print(f"   術語注入: {'✅ ' + str(len(glossary)) + ' 筆' if glossary else '❌ 無'}")
    print(f"   滑動視窗: ✅ 前段 {PREV_CONTEXT_CHARS} 字")
    print()

    t_start = time.time()
    full_translation = translate_novel(llm, chunks, glossary, args.output)
    t_total = time.time() - t_start

    # Summary
    print()
    print("=" * 60)
    print(f"  ✅ 翻譯完成！")
    print(f"  📄 輸出檔案: {args.output}")
    print(f"  📊 共 {len(chunks)} 段 / {len(full_translation)} 字")
    print(f"  ⏱️  總耗時: {t_total:.1f}s ({t_total/60:.1f} 分鐘)")
    print(f"  📈 平均速度: {len(full_translation)/t_total:.0f} 字/秒")
    print("=" * 60)


if __name__ == "__main__":
    main()
