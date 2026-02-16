import sys
import json
import time
from pathlib import Path

# Import MLX dependencies
try:
    from mlx_lm import load, generate
    from mlx_lm.sample_utils import make_sampler
except ImportError:
    print(json.dumps({"error": "mlx_lm library not found. Ensure you are running in venv_mt15."}))
    sys.exit(1)

# Import core logic from novel_translate.py directly to reuse code
# We need to add the project root to sys.path to find novel_translate
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from novel_translate import (
        smart_chunk, 
        build_prompt,
        MAX_CHUNK_CHARS,
        PREV_CONTEXT_CHARS
    )
except ImportError:
    print(json.dumps({"error": "Could not import novel_translate module. Ensure it is in the python path."}))
    sys.exit(1)

DEFAULT_MLX_MODEL = "m-i/HY-MT1.5-7B-mlx-8Bit"

# Generation parameters for HY-MT1.5 (MLX)
# Note: We put sampling params here but will use them to make_sampler
GEN_CONFIG = {
    "temp": 0.7,
    "top_p": 0.6,
    "max_tokens": 2048,
    "verbose": False
}

def translate_chunk_mlx(model, tokenizer, source_chunk: str, glossary: dict, prev_translation: str = "", target_language: str = "繁體中文") -> str:
    """Translate a single chunk using MLX model and HY-MT1.5 prompt logic."""
    
    # 1. Build prompt
    prompt = build_prompt(source_chunk, glossary, prev_translation, target_language=target_language)
    
    # 2. Add 'user' role wrapper
    if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template is not None:
        messages = [{"role": "user", "content": prompt}]
        prompt_formatted = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
    else:
        prompt_formatted = prompt

    # 3. Create Sampler
    # We must explicitly create sampler for this version of mlx_lm
    sampler = make_sampler(temp=GEN_CONFIG["temp"], top_p=GEN_CONFIG["top_p"])

    # 4. Generate
    response = generate(
        model, 
        tokenizer, 
        prompt=prompt_formatted, 
        sampler=sampler,
        max_tokens=GEN_CONFIG["max_tokens"],
        verbose=GEN_CONFIG["verbose"]
    )
    
    return response.strip()

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python translator_worker_mlx.py <input_json_path>"}))
        sys.exit(1)

    try:
        input_path = sys.argv[1]
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 1. Parse Input
        chapters = data.get("chapters", [])
        book_title = data.get("book_title", "Untitled")
        glossary = data.get("glossary", {})
        model_id = data.get("model_id", DEFAULT_MLX_MODEL)
        output_path = data.get("output_path", "translation_result.json")
        target_lang_code = data.get("target_lang", "zh")
        
        # Map code to prompt language name (Official HY-MT1.5 uses Simplified Chinese names)
        # Ref: Supported languages table in docs
        lang_map = {
            "zh": "繁体中文", # or 中文 if unspecified? Docs say 'Traditional Chinese' -> '繁体中文'
            "zh-TW": "繁体中文",
            "zh-CN": "中文",
            "en": "英语",
            "ja": "日语",
            "ko": "韩语",
            "fr": "法语",
            "es": "西班牙语",
            "ru": "俄语",
            "de": "德语"
        }
        target_lang_name = lang_map.get(target_lang_code, "繁体中文")
        
        # 2. Load Model (MLX)
        print(json.dumps({"status": "loading", "message": f"Loading MLX model {model_id}..."}), flush=True)
        model, tokenizer = load(model_id)

        # 3. Translate Title
        print(json.dumps({"status": "translating", "message": f"Translating title: {book_title}..."}), flush=True)
        trans_book_title = translate_chunk_mlx(model, tokenizer, book_title, glossary, prev_translation="", target_language=target_lang_name)

        # 4. Translate Chapters with Sliding Window
        translated_chapters = []
        total_chapters = len(chapters)
        
        global_prev_translation = "" 

        for i, chapter in enumerate(chapters):
            title = chapter.get("title", "")
            text = chapter.get("text", "")
            
            # Update Progress
            print(json.dumps({
                "status": "progress", 
                "message": f"Translating chapter {i+1}/{total_chapters}: {title}", 
                "progress": int((i / total_chapters) * 100)
            }), flush=True)

            # Translate Chapter Title
            trans_title = translate_chunk_mlx(model, tokenizer, title, glossary, prev_translation=global_prev_translation, target_language=target_lang_name)
            
            # Per-paragraph translation with BATCHING for speed
            # Split by double newline (matches how EpubProcessor joined them)
            paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
            translated_paragraphs = []
            
            # Strict 1:1 Paragraph Translation (No Batching)
            # This ensures structure preservation for EPUB replacement
            chapter_char_count = len(text)
            processed_chars = 0
            
            for p_idx, para in enumerate(paragraphs):
                para_len = len(para)
                
                # Skip very short content (likely numbers/whitespace) to save time,
                # but MUST keep 1:1 mapping, so append original or translation
                if para_len < 5 and not any(c.isalpha() for c in para):
                     # Just numbers/symbols -> keep original
                     translated_paragraphs.append(para)
                else:
                     # Translate
                     # Use global context from previous paragraph
                     trans_para = translate_chunk_mlx(model, tokenizer, para, glossary, prev_translation=global_prev_translation, target_language=target_lang_name)
                     translated_paragraphs.append(trans_para)
                     
                     # Update context (keep last 200 chars)
                     global_prev_translation = trans_para[-200:] if len(trans_para) > 200 else trans_para

                processed_chars += para_len
                
                # Update Progress every ~5% or every 10 paragraphs to avoid log spam
                if p_idx % 10 == 0 or p_idx == len(paragraphs) - 1:
                    current_chapter_percent = int((processed_chars / max(1, chapter_char_count)) * 100)
                    total_progress = int(((i + (processed_chars / max(1, chapter_char_count))) / total_chapters) * 100)
                    
                    print(json.dumps({
                        "status": "progress", 
                        "message": f"Translating chapter {i+1}/{total_chapters}: {title} ({current_chapter_percent}%)", 
                        "progress": total_progress
                    }), flush=True)

            full_chapter_text = "\n\n".join(translated_paragraphs)
            
            translated_chapters.append({
                "title": trans_title,
                "text": full_chapter_text
            })

        # 5. Save Result
        result = {
            "book_title": book_title,
            "trans_book_title": trans_book_title,
            "chapters": translated_chapters
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(json.dumps({"status": "completed", "output_path": output_path}), flush=True)

    except Exception as e:
        import traceback
        error_msg = str(e)
        tb = traceback.format_exc()
        print(json.dumps({"status": "error", "error": error_msg, "traceback": tb}), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
