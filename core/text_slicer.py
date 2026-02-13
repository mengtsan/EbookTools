"""
TextSlicer — 3-tier smart text splitting for TTS audiobook generation.

Tier 1: Split by paragraph boundaries (\\n)
Tier 2: Merge short segments (< MIN_CHARS) into previous
Tier 3: Split long segments (> max_chars) at sentence-ending punctuation

Also performs regex-based text cleaning to remove noise characters
that cause TTS artifacts (*, #, ---, etc.)
"""
import re


class TextSlicer:
    # Characters that cause TTS noise / artifacts
    NOISE_PATTERN = re.compile(r'[*#~`|]|^-{3,}$|^={3,}$|^\s*>\s*', re.MULTILINE)
    # Sentence-ending punctuation for secondary splitting
    SENTENCE_END = re.compile(r'([。！？.!?])')
    # Minimum chars — segments shorter than this get merged into previous
    MIN_CHARS = 10

    def __init__(self, max_chars=300):
        """
        Args:
            max_chars: Maximum characters per chunk. Use 300 for CosyVoice3,
                       500 for Qwen3-TTS.
        """
        self.max_chars = max_chars

    def clean_text(self, text: str) -> str:
        """
        Remove noise characters that cause TTS artifacts.
        Preserves meaningful punctuation and whitespace structure.
        """
        if not text:
            return ""

        # Remove markdown-style noise
        cleaned = self.NOISE_PATTERN.sub('', text)

        # Collapse multiple blank lines into double newline
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)

        # Remove leading/trailing whitespace per line but keep structure
        lines = [line.strip() for line in cleaned.split('\n')]
        cleaned = '\n'.join(lines)

        # Final trim
        return cleaned.strip()

    def _split_long_segment(self, segment: str) -> list[str]:
        """
        Tier 3: Split a long segment at sentence-ending punctuation.
        Tries to keep chunks under max_chars while respecting sentence boundaries.
        """
        if len(segment) <= self.max_chars:
            return [segment]

        # Split at sentence-ending punctuation, keeping the delimiter
        parts = self.SENTENCE_END.split(segment)

        chunks = []
        current = ""

        for part in parts:
            if not part:
                continue

            # If adding this part would exceed max, flush current
            if len(current) + len(part) > self.max_chars and current:
                chunks.append(current)
                current = part
            else:
                current += part

        if current:
            chunks.append(current)

        # Safety: if any chunk is still too long (no punctuation found),
        # force-split at max_chars boundary
        final_chunks = []
        for chunk in chunks:
            if len(chunk) > self.max_chars:
                for i in range(0, len(chunk), self.max_chars):
                    sub = chunk[i:i + self.max_chars].strip()
                    if sub:
                        final_chunks.append(sub)
            else:
                final_chunks.append(chunk)

        return final_chunks

    def slice(self, text: str) -> list[str]:
        """
        Main entry point. Returns a list of text chunks ready for TTS.

        Pipeline:
        1. Clean text (remove noise)
        2. Split by paragraph (\\n)
        3. Merge short segments (< MIN_CHARS) into previous
        4. Split long segments (> max_chars) at punctuation
        """
        cleaned = self.clean_text(text)
        if not cleaned:
            return []

        # --- Tier 1: Split by newline ---
        raw_paragraphs = cleaned.split('\n')

        # Remove empty strings
        paragraphs = [p.strip() for p in raw_paragraphs if p.strip()]

        if not paragraphs:
            return []

        # --- Tier 2: Merge short segments ---
        merged = []
        for para in paragraphs:
            if merged and len(para) < self.MIN_CHARS:
                # Merge into previous segment
                merged[-1] = merged[-1] + '，' + para
            else:
                merged.append(para)

        # Edge case: if the first (and only) segment is still very short, keep it
        if not merged:
            return []

        # --- Tier 3: Split long segments at punctuation ---
        final_chunks = []
        for segment in merged:
            if len(segment) > self.max_chars:
                final_chunks.extend(self._split_long_segment(segment))
            else:
                final_chunks.append(segment)

        # Final cleanup: strip each chunk, remove empties
        return [c.strip() for c in final_chunks if c.strip()]
