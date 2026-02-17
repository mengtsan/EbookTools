from fastapi import FastAPI, UploadFile, File, BackgroundTasks, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
import shutil
import os
import uuid
import json
import asyncio
import time
from typing import List

from core.epub_processor import EpubProcessor
from core.tts_engine import MLXEngine
from core.audio_merger import AudioMerger
from core.voice_design import VoiceDesigner
from core.translator_mlx import MLXTranslator

app = FastAPI(title="CosyAudiobook Local Factory")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "output" # Final MP3s
VOICE_DIR = "voices"
TRANSLATION_DIR = "translations"
CHUNK_DIR = "temp_chunks"  # Fault-tolerant chunk cache

for d in [UPLOAD_DIR, OUTPUT_DIR, VOICE_DIR, TRANSLATION_DIR, CHUNK_DIR]:
    os.makedirs(d, exist_ok=True)

# State
tasks = {} # task_id -> {status, progress, message, book_id}
translation_tasks = {} # task_id -> {status, progress, message, filename}

# Initialize Engine (Lazy load)
# We instantiate the class but load weights only when needed or on startup
tts_engine = MLXEngine()
voice_designer = VoiceDesigner()

@app.on_event("startup")
async def startup_event():
    # Preload model if desired, or let it load on first request
    pass

@app.post("/api/upload_epub")
async def upload_epub(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}.epub")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # Parse EPUB
    # We use EpubProcessor which is non-destructive
    try:
        parser = EpubProcessor(file_path)
        chapters = parser.extract_text_segments()
        print(f"DEBUG: Extracted {len(chapters)} chapters/segments")
        
        # Save chapters metadata for later
        meta_path = os.path.join(UPLOAD_DIR, f"{file_id}.json")
        with open(meta_path, "w") as f:
            json.dump({"original_name": file.filename, "file_path": file_path, "chapters": chapters}, f)
            
        return {"book_id": file_id, "chapters": chapters, "filename": file.filename}
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/translate_epub")
async def translate_epub(
    background_tasks: BackgroundTasks,
    book_id: str = Form(...),
    source_lang: str = Form("auto"),
    target_lang: str = Form("zh"),
    model_id: str = Form("m-i/HY-MT1.5-7B-mlx-8Bit")
):
    print(f"DEBUG: Received translation request for book_id={book_id}, target={target_lang}") # Log to stdout
    task_id = str(uuid.uuid4())
    
    translation_tasks[task_id] = {
        "status": "queued",
        "progress": 0,
        "message": "Queued for translation...",
        "output_filename": ""
    }
    
    print(f"DEBUG: Created task {task_id}, queuing background task...")
    background_tasks.add_task(process_translation_task, task_id, book_id, source_lang, target_lang, model_id)
    
    return {"task_id": task_id}

def process_translation_task(task_id, book_id, source_lang, target_lang, model_id):
    print(f"DEBUG: Processing translation task {task_id}...")
    translation_tasks[task_id]["status"] = "processing"
    
    try:
        # Load book metadata to get original name
        meta_path = os.path.join(UPLOAD_DIR, f"{book_id}.json")
        with open(meta_path, 'r') as f:
            book_meta = json.load(f)
            
        original_filename = book_meta.get("original_name", "book.epub")
        book_title = original_filename.replace(".epub", "")
        
        # Resolve the EPUB file path
        input_path = book_meta.get("file_path", os.path.join(UPLOAD_DIR, f"{book_id}.epub"))
        if not os.path.exists(input_path):
            # Fallback: search in upload dir
            for f in os.listdir(UPLOAD_DIR):
                if f.endswith(".epub") and book_id in f:
                    input_path = os.path.join(UPLOAD_DIR, f)
                    break
        
        print(f"DEBUG: Translation input_path={input_path}, exists={os.path.exists(input_path)}")
        
        # Initialize Processor (Structure Preserving)
        processor = EpubProcessor(input_path)
        chapters = processor.extract_text_segments()
        
        # Check extraction
        if not chapters:
            raise HTTPException(status_code=400, detail="No translatable content found in EPUB")
        
        # Initialize Translator (GGUF Engine)
        # Check for user-uploaded glossary or default
        glossary_path = os.path.join(UPLOAD_DIR, "glossary.json")
        glossary = {}
        if os.path.exists(glossary_path):
            with open(glossary_path, 'r', encoding='utf-8') as f:
                try:
                    glossary = json.load(f)
                    print(f"DEBUG: Loaded glossary with {len(glossary)} items")
                except:
                    print("DEBUG: Failed to load glossary.json")
        else:
            # Check project root default
            default_gloss = "glossary.json"
            if os.path.exists(default_gloss):
                with open(default_gloss, 'r', encoding='utf-8') as f:
                    try:
                        glossary = json.load(f)
                        print(f"DEBUG: Loaded default glossary with {len(glossary)} items")
                    except:
                        pass

        translator = MLXTranslator()
        
        def update_progress(p, msg):
            translation_tasks[task_id]["progress"] = p
            translation_tasks[task_id]["message"] = msg
            
        # Run Translation
        translation_tasks[task_id]["message"] = "Initializing MLX Engine..."
        translated_chapters, translated_title = translator.translate_book(
            chapters,
            book_title=book_title,
            glossary=glossary,  # Pass loaded glossary
            target_lang=target_lang,
            progress_callback=update_progress
        )
        
        # Apply translations back to EPUB structure
        translation_tasks[task_id]["message"] = "Reconstructing EPUB..."
        
        output_filename = f"{book_title}_{target_lang}.epub"
        output_path = os.path.join(TRANSLATION_DIR, output_filename)
        
        final_path = processor.apply_translations(translated_chapters, output_path)
        
        # Verify
        if not os.path.exists(final_path):
             raise RuntimeError("Failed to generate EPUB file")
        
        translation_tasks[task_id]["status"] = "completed"
        translation_tasks[task_id]["progress"] = 100
        translation_tasks[task_id]["message"] = "Translation completed!"
        translation_tasks[task_id]["output_filename"] = output_filename
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        translation_tasks[task_id]["status"] = "failed"
        translation_tasks[task_id]["message"] = f"Error: {str(e)}"

@app.get("/api/translation_progress/{task_id}")
async def get_translation_progress(task_id: str):
    async def event_generator():
        while True:
            if task_id not in translation_tasks:
                yield json.dumps({"status": "not_found"})
                break
                
            task = translation_tasks[task_id]
            yield json.dumps(task)
            
            if task["status"] in ["completed", "failed"]:
                break
                
            await asyncio.sleep(1)
            
    return EventSourceResponse(event_generator())

@app.get("/api/download_translation/{filename}")
async def download_translation(filename: str):
    file_path = os.path.join(TRANSLATION_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename)
    raise HTTPException(status_code=404, detail="File not found")

@app.post("/api/upload_voice")
async def upload_voice(file: UploadFile = File(...)):
    voice_id = str(uuid.uuid4())
    ext = file.filename.split('.')[-1]
    file_path = os.path.join(VOICE_DIR, f"{voice_id}.{ext}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {"voice_id": voice_id, "filename": file.filename, "path": file_path}

@app.post("/api/generate")
async def start_generation(
    background_tasks: BackgroundTasks,
    book_id: str = Form(...),
    voice_id: str = Form(None),  # Optional - None means use default voice
    selected_chapters: str = Form(...), # JSON string or comma separated
    model_type: str = Form("qwen3") # qwen3 or cosyvoice3
):
    task_id = str(uuid.uuid4())
    
    # Parse selected chapters
    try:
        selected_ids = json.loads(selected_chapters)
    except:
        selected_ids = selected_chapters.split(',')
        
    tasks[task_id] = {
        "status": "queued",
        "progress": 0,
        "current_chapter": "",
        "current_chapter_index": 0,
        "total_chapters": 0,
        "remaining_chapters": 0,
        "logs": [],
        "remaining_chapters": 0,
        "logs": [],
        "chapter_times": {},
        "current_words_total": 0,
        "current_words_processed": 0
    }
    
    background_tasks.add_task(process_book_task, task_id, book_id, voice_id, selected_ids, model_type)
    
    return {"task_id": task_id}

def process_book_task(task_id, book_id, voice_id, selected_ids, model_type="qwen3"):
    tasks[task_id]["status"] = "processing"
    
    print(f"TRACE: Enter process_book_task task_id={task_id}", flush=True)
    print(f"TRACE: Args: book_id={book_id}, voice_id={voice_id}, model_type={model_type}", flush=True)
    
    try:
        # Load Resources
        epub_path = os.path.join(UPLOAD_DIR, f"{book_id}.epub")
        meta_path = os.path.join(UPLOAD_DIR, f"{book_id}.json")
        
        # Find voice file (optional - None means use default)
        voice_path = None
        if voice_id:
            voice_files = [f for f in os.listdir(VOICE_DIR) if f.startswith(voice_id)]
            if not voice_files:
                raise Exception("Voice file not found")
            voice_path = os.path.join(VOICE_DIR, voice_files[0])
        else:
            # Use default reference if available
            default_ref = os.path.join(VOICE_DIR, "default_ref.wav")
            if os.path.exists(default_ref):
                voice_path = default_ref
            else:
                print("Warning: No voice selected and no default_ref.wav found.")
                voice_path = None
        
        with open(meta_path, 'r') as f:
            book_meta = json.load(f)
            
        all_chapters = book_meta['chapters']
        chapters_to_process = [c for c in all_chapters if str(c['id']) in selected_ids or str(all_chapters.index(c)) in selected_ids] 
        
        if not chapters_to_process:
             chapters_to_process = [c for c in all_chapters if str(c['id']) in selected_ids]

        print(f"TRACE: Total chapters to process: {len(chapters_to_process)}", flush=True)

        total_chapters = len(chapters_to_process)
        book_title = book_meta.get("original_name", "Audiobook").replace(".epub", "")
        
        book_output_dir = os.path.join(OUTPUT_DIR, book_title)
        os.makedirs(book_output_dir, exist_ok=True)
        
        # Ensure correct model is loaded
        print(f"TRACE: Loading model type: {model_type}", flush=True)
        tts_engine.load_model_by_type(model_type)
        print("TRACE: tts_engine.load() calling...", flush=True)
        tts_engine.load()
        print("TRACE: tts_engine loaded.", flush=True)
        
        # Access the internal SubprocessTTSEngine for generate_chapter
        engine = tts_engine._subprocess_engine
        
        tasks[task_id]["total_chapters"] = total_chapters
        
        print("TRACE: Starting chapter loop...", flush=True)
        
        for idx, chapter in enumerate(chapters_to_process):
            print(f"TRACE: Loop idx={idx}, title={chapter['title']}", flush=True)
            tasks[task_id]["current_chapter"] = chapter['title']
            tasks[task_id]["current_chapter_index"] = idx + 1
            tasks[task_id]["remaining_chapters"] = total_chapters - idx
            tasks[task_id]["progress"] = int((idx / total_chapters) * 100)
            
            # Check if final MP3 already exists (chapter-level skip)
            safe_title = re.sub(r'[\\/*?:"<>|]', "", chapter['title'])
            out_filename = f"{idx+1:03d}_{safe_title}.mp3"
            out_path = os.path.join(book_output_dir, out_filename)
            
            if os.path.exists(out_path) and os.path.getsize(out_path) > 1024:
                tasks[task_id]["logs"].append(f"Skipping {chapter['title']} (Exists)")
                print(f"TRACE: Skipping {chapter['title']} (Exists)", flush=True)
                continue

            tasks[task_id]["logs"].append(f"Generating {chapter['title']}...")
            
            # Words tracking
            chapter_text_len = len(chapter['text'])
            print(f"TRACE: Chapter text len: {chapter_text_len}", flush=True)
            tasks[task_id]["current_words_total"] = chapter_text_len
            tasks[task_id]["current_words_processed"] = 0
            
            start_time = time.time()
            
            # --- New v0.3.0 Pipeline: generate_chapter + AudioMerger ---
            
            # Create chunk directory for this chapter (fault tolerance)
            chapter_chunk_dir = os.path.join(
                CHUNK_DIR, task_id, f"ch_{idx:03d}"
            )
            
            # Progress callback to update task state
            def on_chunk_progress(chunk_idx, total_chunks, chunk_text):
                processed = int((chunk_idx + 1) / total_chunks * chapter_text_len)
                tasks[task_id]["current_words_processed"] = processed
            
            # Generate all chunks (with crash-resume: skips existing valid chunks)
            print("TRACE: Calling engine.generate_chapter...", flush=True)
            chunk_dir = engine.generate_chapter(
                text=chapter['text'],
                ref_audio_path=voice_path,
                chunk_dir=chapter_chunk_dir,
                progress_callback=on_chunk_progress
            )
            print("TRACE: engine.generate_chapter returned.", flush=True)
            
            # Merge chunks into final MP3 using ffmpeg
            tags = {
                'title': chapter['title'],
                'artist': 'CosyVoice AI',
                'album': book_title
            }
            AudioMerger.merge_chunks(
                chunk_dir=chunk_dir,
                output_path=out_path,
                silence_ms=300,
                bitrate="192k",
                tags=tags
            )
            
            # Clean up chunk directory after successful merge
            AudioMerger.cleanup(chunk_dir)
            
            elapsed = time.time() - start_time
            tasks[task_id]["chapter_times"][str(chapter['id'])] = f"{elapsed:.1f}s"
            tasks[task_id]["logs"].append(f"Chapter completed in {elapsed:.1f}s")
            
        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["logs"].append("All chapters completed.")
        
        # Clean up task-level chunk directory
        task_chunk_dir = os.path.join(CHUNK_DIR, task_id)
        AudioMerger.cleanup(task_chunk_dir)
        
    except Exception as e:
        import traceback
        error_msg = f"Task failed: {e}\n{traceback.format_exc()}"
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["error"] = str(e)
        tasks[task_id]["logs"].append(f"Error: {str(e)}")
        # NOTE: Chunk directory is preserved on failure for crash-resume
        print(f"\n!!!!!!!!!!!! TASK FAILED !!!!!!!!!!!!\nError details: {str(e)}\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")
        print(error_msg)
        try:
             with open("backend_error.log", "w") as f:
                 f.write(error_msg)
        except:
             pass

@app.post("/api/voice_design/generate")
async def generate_voice_design_api(
    text: str = Form(...),
    instruct: str = Form(...),
    language: str = Form("Chinese")
):
    try:
        # Generate
        # output_path, gen_id = voice_designer.generate(text, instruct, language)
        # Run in threadpool to avoid blocking
        loop = asyncio.get_event_loop()
        output_path, gen_id = await loop.run_in_executor(None, voice_designer.generate, text, instruct, language)
        
        # We need to return a URL to play it. 
        # Since 'uploads' is served via static? No, static serves 'static' folder.
        # We need to serve 'uploads' as well or copy to static?
        # Actually existing uploads are not served directly usually?
        # Let's check where UPLOAD_DIR is. It's "uploads".
        # We should mount uploads or return a file response endpoint.
        # Let's mount uploads for easy access or use a specific playback endpoint.
        
        # Quick fix: copy to static/temp for playback or Serve file.
        # Better: just return the filename and have a /api/audio/{filename} endpoint.
        
        return {"status": "success", "gen_id": gen_id, "path": output_path, "filename": os.path.basename(output_path)}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/voice_design/save_as_ref")
async def save_voice_ref_api(
    gen_id: str = Form(...), # or filename
    name: str = Form(...)
):
    try:
        # Find file
        # Check generated file exists.
        # We assumed path was returned. frontend sends path or gen_id.
        # Ideally frontend sends gen_id, we reconstruct path.
        filename = f"design_{gen_id}.wav"
        output_path = os.path.join(UPLOAD_DIR, filename)
        
        if not os.path.exists(output_path):
            raise HTTPException(status_code=404, detail="Generated audio validation failed or expired.")
            
        saved_name = voice_designer.save_as_voice(output_path, name)
        return {"status": "success", "saved_name": saved_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/audio/{filename}")
async def get_audio_file(filename: str):
    file_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    # Check voices too?
    voice_path = os.path.join(VOICE_DIR, filename)
    if os.path.exists(voice_path):
        return FileResponse(voice_path)
    raise HTTPException(status_code=404, detail="File not found")


@app.get("/api/progress/{task_id}")
async def get_progress(task_id: str):
    async def event_generator():
        while True:
            if task_id not in tasks:
                yield json.dumps({"status": "not_found"})
                break
                
            task = tasks[task_id]
            data = json.dumps(task)
            yield data
            
            if task["status"] in ["completed", "failed"]:
                break
                
            await asyncio.sleep(1)
            
    return EventSourceResponse(event_generator())

# Mount static files last to allow API routes to take precedence
app.mount("/", StaticFiles(directory="static", html=True), name="static")

import re

# Ensure ffmpeg is available (fail-fast)
try:
    subprocess_result = __import__('subprocess').run(
        ['ffmpeg', '-version'], capture_output=True, text=True
    )
    if subprocess_result.returncode != 0:
        print("WARNING: ffmpeg not found. Audio merging will fail. Install with: brew install ffmpeg")
except FileNotFoundError:
    print("WARNING: ffmpeg not found. Audio merging will fail. Install with: brew install ffmpeg")
