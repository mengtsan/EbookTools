"""
AudioMerger — ffmpeg-based audio chunk concatenation for audiobook generation.

Merges per-chunk WAV files into a final MP3, inserting silence between chunks
for natural pacing. Uses ffmpeg-python for reliable audio processing.
"""
import os
import glob
import shutil
import tempfile
import subprocess


class AudioMerger:
    """Merge WAV chunks into a single MP3 using ffmpeg."""

    @staticmethod
    def _get_sorted_chunks(chunk_dir: str) -> list[str]:
        """Get chunk WAV files sorted by index (chunk_0001.wav, chunk_0002.wav, ...)."""
        pattern = os.path.join(chunk_dir, "chunk_*.wav")
        chunks = sorted(glob.glob(pattern))
        return chunks

    @staticmethod
    def _generate_silence(duration_ms: int, sample_rate: int = 24000,
                          output_path: str = None) -> str:
        """Generate a silent WAV file of specified duration using ffmpeg."""
        if output_path is None:
            output_path = tempfile.mktemp(suffix="_silence.wav")

        duration_s = duration_ms / 1000.0
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"anullsrc=r={sample_rate}:cl=mono",
            "-t", str(duration_s),
            "-ar", str(sample_rate),
            "-ac", "1",
            "-sample_fmt", "s16",
            output_path
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return output_path

    @staticmethod
    def merge_chunks(chunk_dir: str, output_path: str,
                     silence_ms: int = 300, bitrate: str = "192k",
                     sample_rate: int = 24000,
                     tags: dict = None) -> str:
        """
        Merge all chunk_*.wav files in chunk_dir into a single MP3.

        Args:
            chunk_dir: Directory containing chunk_XXXX.wav files
            output_path: Path for the output MP3 file
            silence_ms: Milliseconds of silence between chunks (default 300ms)
            bitrate: MP3 bitrate (default "192k")
            sample_rate: Audio sample rate (default 24000 Hz)
            tags: Optional dict of MP3 metadata tags (title, artist, album)

        Returns:
            Path to the output MP3 file

        Raises:
            FileNotFoundError: If no chunks found in chunk_dir
            subprocess.CalledProcessError: If ffmpeg fails
        """
        chunks = AudioMerger._get_sorted_chunks(chunk_dir)
        if not chunks:
            raise FileNotFoundError(f"No chunk_*.wav files found in {chunk_dir}")

        print(f"Merging {len(chunks)} chunks from {chunk_dir} -> {output_path}")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Generate silence file for padding
        silence_path = None
        concat_list_path = None

        try:
            # Create silence WAV
            silence_path = AudioMerger._generate_silence(
                silence_ms, sample_rate,
                os.path.join(chunk_dir, "_silence.wav")
            )

            # Build ffmpeg concat demuxer file list
            concat_list_path = os.path.join(chunk_dir, "_concat_list.txt")
            with open(concat_list_path, 'w') as f:
                for i, chunk_path in enumerate(chunks):
                    # Use absolute paths and escape single quotes
                    abs_path = os.path.abspath(chunk_path)
                    f.write(f"file '{abs_path}'\n")
                    # Add silence after each chunk (including last for consistent ending)
                    if silence_path and i < len(chunks) - 1:
                        abs_silence = os.path.abspath(silence_path)
                        f.write(f"file '{abs_silence}'\n")

            # Run ffmpeg concat + encode to MP3
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_list_path,
                "-ar", str(sample_rate),
                "-ac", "1",
                "-b:a", bitrate,
            ]

            # Add metadata tags
            if tags:
                for key, value in tags.items():
                    cmd.extend(["-metadata", f"{key}={value}"])

            cmd.append(output_path)

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise subprocess.CalledProcessError(
                    result.returncode, cmd, result.stdout, result.stderr
                )

            print(f"Merge complete: {output_path} ({os.path.getsize(output_path)} bytes)")
            return output_path

        finally:
            # Clean up temp files (silence + concat list), but NOT the chunks
            for tmp in [silence_path, concat_list_path]:
                if tmp and os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass

    @staticmethod
    def cleanup(chunk_dir: str):
        """Remove the entire chunk directory after successful merge."""
        if os.path.isdir(chunk_dir):
            print(f"Cleaning up chunk directory: {chunk_dir}")
            shutil.rmtree(chunk_dir, ignore_errors=True)
