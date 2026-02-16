import subprocess
import json
import os
import sys
import tempfile
from pathlib import Path

class MLXTranslator:
    def __init__(self, model_id="m-i/HY-MT1.5-7B-mlx-8Bit"):
        self.model_id = model_id
        
        # Path to the specific venv for MLX translation (venv_mt15)
        # Project root is assumed to be two levels up from this file (core/translator_mlx.py -> core -> root)
        self.project_root = Path(__file__).resolve().parent.parent
        self.venv_python = self.project_root / "venv_mt15" / "bin" / "python"
        self.worker_script = self.project_root / "core" / "translator_worker_mlx.py"

    def translate_book(self, chapters, book_title="", glossary=None, target_lang="zh", progress_callback=None):
        """
        Translate a list of chapters using the MLX worker script.
        
        Args:
            chapters: list of dict {'title': str, 'text': str}
            book_title: str
            glossary: dict or None
            target_lang: str (e.g. 'zh', 'en', 'ja')
            progress_callback: function(progress_int, message_str)
            
        Returns: 
            (translated_chapters, translated_book_title)
        """
        if not os.path.exists(self.venv_python):
            raise RuntimeError(f"MLX Translation venv not found at {self.venv_python}. Please check setup.")

        # Prepare input payload
        input_data = {
            "chapters": chapters,
            "book_title": book_title,
            "glossary": glossary or {},
            "model_id": self.model_id,
            "target_lang": target_lang,
            "output_path": ""  # Will set temp path below
        }

        # Create temp files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f_in:
            json.dump(input_data, f_in, ensure_ascii=False)
            input_tmp_path = f_in.name
            
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f_out:
            output_tmp_path = f_out.name
            
        # Update output path in input file
        input_data["output_path"] = output_tmp_path
        with open(input_tmp_path, 'w', encoding='utf-8') as f:
            json.dump(input_data, f, ensure_ascii=False)

        try:
            # Run worker in subprocess
            # We set PYTHONPATH to project root so worker can import novel_translate
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root) + os.pathsep + env.get("PYTHONPATH", "")
            
            process = subprocess.Popen(
                [str(self.venv_python), str(self.worker_script), input_tmp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                bufsize=1  # Line buffered
            )

            # Monitor stdout for progress
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                
                if line:
                    line = line.strip()
                    try:
                        # Try to parse JSON from stdout
                        if line.startswith('{') and line.endswith('}'):
                            data = json.loads(line)
                            status = data.get("status")
                            
                            if status == "progress":
                                if progress_callback:
                                    progress_callback(data.get("progress", 0), data.get("message", ""))
                            elif status == "error":
                                raise RuntimeError(f"MLX Worker Error: {data.get('error')}\n{data.get('traceback')}")
                            elif status == "loading":
                                if progress_callback:
                                    progress_callback(0, data.get("message"))
                            elif status == "translating":
                                if progress_callback:
                                    progress_callback(0, data.get("message"))
                        else:
                            # Forward non-JSON output (like mlx logs) to console/logs if needed
                            print(f"[MLX Worker Log] {line}")
                            
                    except json.JSONDecodeError:
                        print(f"[MLX Worker raw] {line}")

            if process.returncode != 0:
                stderr = process.stderr.read()
                raise RuntimeError(f"Translation failed with exit code {process.returncode}\nStderr: {stderr}")

            # Read Output
            if os.path.exists(output_tmp_path):
                with open(output_tmp_path, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                    return result.get("chapters", []), result.get("trans_book_title", book_title)
            else:
                raise RuntimeError("Output file was not created by the worker.")

        finally:
            # Cleanup temp files
            if os.path.exists(input_tmp_path):
                os.remove(input_tmp_path)
            if os.path.exists(output_tmp_path):
                os.remove(output_tmp_path)
