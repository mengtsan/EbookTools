from pydub import AudioSegment
import numpy as np
import os

class AudioPostProcessor:
    @staticmethod
    def numpy_to_audio_segment(audio_data, frame_rate=24000):
        """
        Convert float32/float16 numpy array (from MLX) to pydub AudioSegment.
        """
        # Ensure numpy array
        if not isinstance(audio_data, np.ndarray):
            audio_data = np.array(audio_data)
            
        # Normalize if needed? Usually MLX outputs -1.0 to 1.0 floats
        # Convert to int16 PCM
        # audio_data might be float32 or float16
        
        # Clip to avoid overflow
        audio_data = np.clip(audio_data, -1.0, 1.0)
        
        audio_int16 = (audio_data * 32767).astype(np.int16)
        
        return AudioSegment(
            audio_int16.tobytes(),
            frame_rate=frame_rate,
            sample_width=2, # 2 bytes = 16 bit
            channels=1
        )

    @staticmethod
    def save_mp3(segments, output_path, tags=None):
        """
        Combine segments and save as MP3.
        segments: list of AudioSegment objects
        """
        if not segments:
            print(f"No audio segments to save for {output_path}")
            return
            
        final_audio = AudioSegment.empty()
        
        # Create silent segment (250ms) to pad between chunks
        silence = AudioSegment.silent(duration=250, frame_rate=24000)
        
        for i, seg in enumerate(segments):
            final_audio += seg
            # Add silence after each segment except the last one (or maybe even the last?)
            # Adding to all ensures separation.
            final_audio += silence
            
        # Create directory if needed
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        print(f"Exporting MP3 to {output_path}...")
        final_audio.export(
            output_path,
            format="mp3",
            bitrate="192k",
            tags=tags
        )
