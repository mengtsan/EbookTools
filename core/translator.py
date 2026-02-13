import subprocess
import json
import os
import sys
import tempfile
import uuid

class SubprocessTranslator:
    def __init__(self, model_id="m-i/HY-MT1.5-7B-mlx-8Bit"):
        self.model_id = model_id
        # Use isolated environment for MT1.5 if available, else fallback
        venv_python = os.path.abspath("./venv_mt15/bin/python")
        if os.path.exists(venv_python):
             self.python_executable = venv_python
        else:
             self.python_executable = sys.executable

    def translate_book(self, chapters, book_title="", source_lang="auto", target_lang="zh", progress_callback=None):
        """
        Translate a list of chapters using the worker script.
        chapters: list of dict {'title': str, 'text': str}
        Returns: (translated_chapters, translated_book_title)
        """
        script_path = os.path.join(os.path.dirname(__file__), "translator_worker.py")
        
        # Create temp files
        input_file = tempfile.mktemp(suffix=".json")
        output_file = tempfile.mktemp(suffix=".json")

        params = {
            "chapters": chapters,
            "book_title": book_title, # Pass title
            "source_lang": source_lang,
            "target_lang": target_lang,
            "model_id": self.model_id,
            "output_path": output_file
        }
        
        with open(input_file, 'w') as f:
            json.dump(params, f)

        try:
            # Run subprocess with Popen to read stdout in real-time
            process = subprocess.Popen(
                [self.python_executable, script_path, input_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Read stdout line by line
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                
                if line:
                    try:
                        data = json.loads(line.strip())
                        if data.get("status") == "progress":
                            if progress_callback:
                                progress_callback(data.get("progress", 0), data.get("message", ""))
                        elif data.get("status") == "error":
                            raise RuntimeError(f"Translation worker error: {data.get('error')}")
                    except json.JSONDecodeError:
                        # print(f"Worker output: {line.strip()}") # Debug
                        pass
            
            if process.returncode != 0:
                stderr = process.stderr.read()
                raise RuntimeError(f"Translation subprocess failed with code {process.returncode}: {stderr}")

            # Read result
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    result = json.load(f)
                    # Return tuple: (chapters, translated_title)
                    return result.get("chapters", []), result.get("trans_book_title", book_title)
            else:
                raise RuntimeError("Translation output file not found")

        finally:
            # Cleanup
            if os.path.exists(input_file):
                os.remove(input_file)
            if os.path.exists(output_file):
                os.remove(output_file)

