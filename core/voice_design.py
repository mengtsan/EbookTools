import os
import subprocess
import json
import uuid
import tempfile
import sys

class VoiceDesigner:
    def __init__(self, model_id="mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16"):
        self.model_id = model_id
        # Use venv_qwen3 if available, else fallback to sys.executable
        venv_python = os.path.abspath("./venv_qwen3/bin/python")
        if os.path.exists(venv_python):
             self.python_executable = venv_python
        else:
             self.python_executable = sys.executable
        
    def load(self):
        # No-op in subprocess mode
        pass

    def generate(self, text, instruct, language="Chinese"):
        """
        Generates audio via subprocess.
        Returns: Tuple (output_path, voice_id)
        """
        gen_id = str(uuid.uuid4())
        
        # Output directory
        output_dir = "uploads" 
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.abspath(os.path.join(output_dir, f"design_{gen_id}.wav"))
        
        # Prepare input for worker
        params = {
            "text": text,
            "instruct": instruct,
            "language": language,
            "output_path": output_path,
            "model_id": self.model_id
        }
        
        # Temp input file
        with tempfile.NamedTemporaryFile(mode='w', suffix=".json", delete=False) as f:
            json.dump(params, f)
            input_file = f.name
            
        script_path = os.path.join(os.path.dirname(__file__), "voice_design_worker.py")
        
        try:
            print(f"Running VoiceDesign subprocess: {self.python_executable} {script_path}")
            process = subprocess.Popen(
                [self.python_executable, script_path, input_file],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Read streaming output
            last_status = {}
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                
                if line:
                    try:
                        data = json.loads(line.strip())
                        last_status = data
                        if data.get("status") == "error":
                            raise RuntimeError(f"VoiceDesign Worker Error: {data.get('error')}\n{data.get('traceback', '')}")
                        elif data.get("status") in ["loading", "generating"]:
                            print(f"[VoiceDesign] {data.get('message')}")
                    except json.JSONDecodeError:
                        print(f"[VoiceDesign Worker Output] {line.strip()}")
            
            if process.returncode != 0:
                stderr = process.stderr.read()
                raise RuntimeError(f"VoiceDesign subprocess failed (code {process.returncode}): {stderr}")
                
            if os.path.exists(output_path):
                return output_path, gen_id
            else:
                 raise RuntimeError("VoiceDesign worker finished but output file missing.")
                 
        finally:
            if os.path.exists(input_file):
                os.remove(input_file)

    def save_as_voice(self, generated_path, voice_name):
        """
        Saves the generated audio as a reference voice for cloning.
        """
        import shutil
        voice_dir = "voices"
        os.makedirs(voice_dir, exist_ok=True)
        
        # Sanitize name
        safe_name = "".join([c for c in voice_name if c.isalpha() or c.isdigit() or c in (' ', '_', '-')]).strip()
        filename = f"{safe_name}.wav"
        dest_path = os.path.join(voice_dir, filename)
        
        if os.path.exists(dest_path):
            # Append random id if exists
            filename = f"{safe_name}_{uuid.uuid4().hex[:4]}.wav"
            dest_path = os.path.join(voice_dir, filename)
            
        shutil.copy(generated_path, dest_path)
        return filename
