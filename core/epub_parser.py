import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
import os
import re

class EbookParser:
    def __init__(self, filepath):
        self.filepath = filepath
        self.book = None
        
    def _load_book(self):
        try:
            self.book = epub.read_epub(self.filepath)
        except Exception as e:
            raise RuntimeError(f"Failed to load EPUB: {e}")

    def _is_skippable(self, title, soup):
        """
        Smart algorithm to determine if a chapter should be skipped (TOC, Copyright, etc.)
        """
        text = soup.get_text().strip()
        total_chars = len(text)
        
        # 0. Safety check for empty content
        if total_chars == 0:
            return True

        # 1. Keyword Check (Title)
        if title:
            title_lower = title.lower()
            skip_keywords = [
                'contents', 'table of contents', 'copyright', 'index', 'dedication', 
                'preface', 'acknowledgments', '目錄', '索引', '版權', '致謝', '封面', 
                '推薦序', '作者簡介'
            ]
            if any(k in title_lower for k in skip_keywords):
                return True

        # 2. Content Analysis
        # Link Density: TOCs usually have high link density
        links = soup.find_all('a')
        link_text_length = sum(len(a.get_text()) for a in links)
        
        if total_chars > 0:
            link_density = link_text_length / total_chars
            if link_density > 0.4: # Threshold: 40% of text is links
                return True

        # 3. Length Check
        # Very short chapters might be page separators or copyright notices
        # But be careful not to skip actual short chapters (like "Epilogue")
        # Ensure we don't accidentally skip a short prologue if it didn't hit keywords
        if total_chars < 100 and (not title or "chapter" not in title.lower()):
            return True
            
        return False

    def parse(self):
        if not self.book:
            self._load_book()
            
        # Get the spine (linear reading order)
        # The spine contains Item objects or identifiers
        spine_ids = [item[0] for item in self.book.spine if item[1] == 'yes'] # item[1] is 'linear' property ('yes'/'no')

        chapters = []
        
        for item_id in spine_ids:
            item = self.book.get_item_with_id(item_id)
            if not item:
                continue
                
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                content = item.get_content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Extract Title
                # Try h1-h6, then title tag
                title_tag = soup.find(['h1', 'h2', 'h3', 'title'])
                title = title_tag.get_text().strip() if title_tag else f"Section {len(chapters) + 1}"
                
                # Clean text
                # Replace block tags with newlines to preserve structure
                for tag in soup.find_all(['p', 'div', 'br', 'li']):
                    tag.append('\n')
                
                raw_text = soup.get_text()
                
                # Post-processing cleaning
                # Remove extra newlines
                clean_text = re.sub(r'\n{3,}', '\n\n', raw_text).strip()
                
                if not clean_text:
                    continue
                    
                is_skippable = self._is_skippable(title, soup)
                
                chapters.append({
                    "id": item_id,
                    "title": title,
                    "text": clean_text,
                    "skippable": is_skippable,
                    "word_count": len(clean_text)
                })
                
        return chapters
