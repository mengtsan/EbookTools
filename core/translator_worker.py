import sys
import json
import mlx.core as mx
from mlx_lm import load, generate

def translate_text(model, tokenizer, text, source_lang, target_lang):
    if not text.strip():
        return ""
    
    target_lang_name = {
        "zh": "Chinese",
        "en": "English",
        "ja": "Japanese",
        "ko": "Korean", 
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "ru": "Russian",
        "th": "Thai",
        "vi": "Vietnamese",
        "zh-TW": "Traditional Chinese"
    }.get(target_lang, target_lang)

    # Split into paragraphs to avoid context length issues and preserve structure
    paragraphs = text.split('\n')
    translated_paragraphs = []
    
    for p in paragraphs:
        if not p.strip():
            translated_paragraphs.append("")
            continue
            
        prompt = f"Translate the following text into {target_lang_name}. Output ONLY the translation, no explanation.\n\n{p}"
        
        if hasattr(tokenizer, "apply_chat_template") and tokenizer.chat_template is not None:
             messages = [{"role": "user", "content": prompt}]
             prompt = tokenizer.apply_chat_template(
                 messages, tokenize=False, add_generation_prompt=True
             )
        
        # Lower max_tokens for paragraphs to speed it up, but need to be safe
        response = generate(model, tokenizer, prompt=prompt, verbose=False, max_tokens=1024)
        translated_paragraphs.append(response.strip())
        
    return "\n".join(translated_paragraphs)

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python translator_worker.py <input_json_path>"}))
        sys.exit(1)

    try:
        input_path = sys.argv[1]
        with open(input_path, 'r') as f:
            data = json.load(f)
            
        source_lang = data.get("source_lang", "auto")
        target_lang = data.get("target_lang", "zh")
        model_id = data.get("model_id", "m-i/HY-MT1.5-7B-mlx-8Bit")
        chapters = data.get("chapters", [])
        book_title = data.get("book_title", "") # Get book title
        output_path = data.get("output_path", "translation_result.json")

        print(json.dumps({"status": "loading", "message": f"Loading model {model_id}..."}), flush=True)
        
        # Load model
        model, tokenizer = load(model_id)
        
        print(json.dumps({"status": "translating", "message": "Starting translation..."}), flush=True)
        
        # Translate Book Title
        trans_book_title = book_title
        if book_title:
             print(json.dumps({"status": "progress", "message": f"Translating book title: {book_title}...", "progress": 0}), flush=True)
             trans_book_title = translate_text(model, tokenizer, book_title, source_lang, target_lang)

        translated_chapters = []
        total = len(chapters)
        
        for i, chapter in enumerate(chapters):
            title = chapter.get("title", "")
            text = chapter.get("text", "")
            
            # Translate Title
            trans_title = translate_text(model, tokenizer, title, source_lang, target_lang)
            
            # Translate Text
            print(json.dumps({"status": "progress", "message": f"Translating chapter {i+1}/{total}: {title}", "progress": (i/total)*100}), flush=True)
            trans_text = translate_text(model, tokenizer, text, source_lang, target_lang)
            
            translated_chapters.append({
                "title": trans_title,
                "text": trans_text
            })

        # Save result
        with open(output_path, 'w') as f:
            json.dump({
                "chapters": translated_chapters,
                "trans_book_title": trans_book_title
            }, f)

        print(json.dumps({"status": "completed", "output_path": output_path}), flush=True)

    except Exception as e:
        import traceback
        print(json.dumps({"status": "error", "error": str(e), "traceback": traceback.format_exc()}), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
