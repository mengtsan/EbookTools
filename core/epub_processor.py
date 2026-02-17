"""
EpubProcessor: ZIP-based EPUB modification for structure-preserving translation.

Instead of using ebooklib (which rewrites the entire EPUB structure),
this module treats EPUB as a ZIP archive and modifies HTML files in-place.
All CSS, images, TOC, fonts, and metadata are preserved byte-for-byte.
"""
import os
import re
import zipfile
import shutil
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup


class EpubProcessor:
    """
    Handles EPUB load -> extract text -> apply translations -> save cycle
    using direct ZIP manipulation for perfect structure preservation.
    """

    # Tags whose text content we extract and translate
    # Tags whose text content we extract and translate
    # Added 'a' to translate link text individually without destroying hrefs
    TRANSLATABLE_TAGS = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a']

    def __init__(self, filepath):
        self.filepath = filepath
        # Maps: item_href -> list of paragraph texts (original)
        self.item_segments = {}
        # Stores the OPF rootfile path and spine info
        self.opf_path = None
        self.opf_dir = ""  # Directory containing OPF (for resolving relative hrefs)
        self.spine_hrefs = []  # Ordered list of HTML file paths in ZIP

    def _parse_container(self, zf):
        """Parse META-INF/container.xml to find the OPF file path."""
        with zf.open("META-INF/container.xml") as f:
            tree = ET.parse(f)
        
        ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
        rootfile = tree.find(".//c:rootfile", ns)
        if rootfile is None:
            # Try without namespace (some EPUBs)
            rootfile = tree.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
        if rootfile is None:
            raise RuntimeError("Cannot find rootfile in container.xml")
        
        self.opf_path = rootfile.get("full-path")
        self.opf_dir = os.path.dirname(self.opf_path)

    def _parse_opf(self, zf):
        """Parse the OPF file to get spine reading order and manifest items."""
        with zf.open(self.opf_path) as f:
            tree = ET.parse(f)
        
        root = tree.getroot()
        # Handle OPF namespace
        ns_match = re.match(r'\{(.+)\}', root.tag)
        ns = ns_match.group(1) if ns_match else ""
        nsmap = {"opf": ns} if ns else {}
        
        # Build manifest: id -> href
        manifest = {}
        for item in root.iter(f"{{{ns}}}item" if ns else "item"):
            item_id = item.get("id")
            href = item.get("href")
            media_type = item.get("media-type", "")
            if item_id and href:
                manifest[item_id] = {"href": href, "media_type": media_type}
        
        # Get spine order
        self.spine_hrefs = []
        for itemref in root.iter(f"{{{ns}}}itemref" if ns else "itemref"):
            idref = itemref.get("idref")
            linear = itemref.get("linear", "yes")
            if idref in manifest and linear != "no":
                href = manifest[idref]["href"]
                # Resolve relative to OPF directory
                full_path = os.path.join(self.opf_dir, href) if self.opf_dir else href
                # Normalize path separators
                full_path = full_path.replace("\\", "/")
                self.spine_hrefs.append(full_path)

    def extract_text_segments(self):
        """
        Open the EPUB ZIP, parse spine HTML files, and extract translatable
        text segments (paragraph-level).
        
        Returns a list of 'chapter' dicts compatible with the translator worker:
        [{"id": zip_path, "title": str, "text": str, "paragraphs": [str,...],
          "word_count": int, "skippable": bool}]
        """
        zf = zipfile.ZipFile(self.filepath, 'r')
        self._parse_container(zf)
        self._parse_opf(zf)
        
        chapters = []
        
        for href in self.spine_hrefs:
            try:
                html_bytes = zf.read(href)
            except KeyError:
                # Try without leading directory
                alt = href.lstrip("/")
                try:
                    html_bytes = zf.read(alt)
                    href = alt
                except KeyError:
                    continue
            
            soup = BeautifulSoup(html_bytes, 'html.parser')
            
            # Extract translatable paragraphs
            paragraphs = []
            
            # 1. Extract <title> content
            title_tag = soup.find('title')
            if title_tag and title_tag.get_text().strip():
                paragraphs.append(title_tag.get_text().strip())

            # 2. Extract block-level text tags (simple, reliable)
            for tag in soup.find_all(self.TRANSLATABLE_TAGS):
                # Skip tags containing images or other complex elements
                # ALSO SKIP tags containing 'a' (links) if the tag itself is not 'a'
                # This prevents <p><a>...</a></p> from being wiped. We will process <a> separately.
                if tag.name != 'a' and tag.find('a'):
                    continue
                
                if tag.find(['img', 'image', 'svg', 'table', 'pre', 'code']):
                    continue
                
                text = tag.get_text().strip()
                if text:
                    paragraphs.append(text)
            
            if not paragraphs:
                continue
            
            # Store segment info
            self.item_segments[href] = paragraphs
            
            full_text = "\n\n".join(paragraphs)
            
            # Extract internal title for list display
            item_title = "Untitled"
            h_tag = soup.find(['h1', 'h2'])
            if h_tag:
                item_title = h_tag.get_text().strip()
            elif title_tag:
                item_title = title_tag.get_text().strip()

            chapters.append({
                "id": href,
                "title": item_title,
                "text": full_text,
                "paragraphs": paragraphs,
                "word_count": len(full_text),
                "skippable": False
            })
            
        # 3. Process TOC (NCX) if exists
        ncx_href = None
        for name in zf.namelist():
            if name.endswith('.ncx'):
                ncx_href = name
                break
        
        if ncx_href:
            try:
                ncx_bytes = zf.read(ncx_href)
                soup = BeautifulSoup(ncx_bytes, 'xml') 
                paragraphs = []
                
                for text_tag in soup.find_all('text'):
                    text = text_tag.get_text().strip()
                    if text:
                        paragraphs.append(text)
                
                if paragraphs:
                    self.item_segments[ncx_href] = paragraphs
                    full_text = "\n\n".join(paragraphs)
                    chapters.append({
                        "id": ncx_href,
                        "title": "TOC (Navigation)",
                        "text": full_text,
                        "paragraphs": paragraphs,
                        "word_count": len(full_text),
                        "skippable": False
                    })
            except Exception as e:
                print(f"Error processing NCX {ncx_href}: {e}")

        # 4. Process OPF Metadata
        if self.opf_path:
            try:
                opf_bytes = zf.read(self.opf_path)
                soup = BeautifulSoup(opf_bytes, 'xml')
                paragraphs = []
                
                for tag_name in ['title', 'creator', 'description', 'subject']:
                    for tag in soup.find_all(tag_name):
                        text = tag.get_text().strip()
                        if text:
                            paragraphs.append(text)
                
                if paragraphs:
                    self.item_segments[self.opf_path] = paragraphs
                    full_text = "\n\n".join(paragraphs)
                    chapters.append({
                        "id": self.opf_path,
                        "title": "Book Metadata",
                        "text": full_text,
                        "paragraphs": paragraphs,
                        "word_count": len(full_text),
                        "skippable": False
                    })
            except Exception as e:
                print(f"Error processing OPF {self.opf_path}: {e}")

        zf.close()
        return chapters

    def apply_translations(self, translated_chapters, output_path):
        """
        Apply translations back to the EPUB by modifying HTML files in the ZIP.
        
        Strategy:
        - Copy the entire original ZIP to output_path
        - For each translated chapter, parse the corresponding HTML,
          find matching <p>/<h> tags, and replace text content
        - Write modified HTML back into the ZIP
        
        This preserves ALL non-HTML files (CSS, images, fonts, NCX, OPF) exactly.
        """
        # Step 1: Copy original EPUB to output
        shutil.copy2(self.filepath, output_path)
        
        # Build translation map: href -> translated paragraphs
        trans_map = {}
        for i, chapter in enumerate(translated_chapters):
            href_keys = list(self.item_segments.keys())
            if i < len(href_keys):
                href = href_keys[i]
                trans_text = chapter.get("text", "")
                trans_paragraphs = [p.strip() for p in trans_text.split("\n\n") if p.strip()]
                trans_map[href] = trans_paragraphs
        
        # Step 2: Rebuild the ZIP with modified files
        temp_dir = tempfile.mkdtemp()
        temp_epub = os.path.join(temp_dir, "output.epub")
        
        try:
            with zipfile.ZipFile(output_path, 'r') as zf_in:
                with zipfile.ZipFile(temp_epub, 'w') as zf_out:
                    for item in zf_in.infolist():
                        data = zf_in.read(item.filename)
                        
                        if item.filename in trans_map:
                            orig_segs = self.item_segments.get(item.filename, [])
                            trans_segs = trans_map[item.filename]
                            
                            if item.filename.endswith('.ncx') or item.filename.endswith('.opf'):
                                data = self._apply_to_xml(data, orig_segs, trans_segs)
                            else:
                                data = self._apply_to_html(data, orig_segs, trans_segs)
                        
                        zf_out.writestr(item, data)
            
            shutil.move(temp_epub, output_path)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        return output_path

    def _apply_to_xml(self, xml_bytes, orig_paragraphs, trans_paragraphs):
        """Apply translations to XML (NCX/OPF) files using regex replacement."""
        content = xml_bytes.decode('utf-8')
        
        count = min(len(orig_paragraphs), len(trans_paragraphs))
        for i in range(count):
            orig = orig_paragraphs[i].strip()
            trans = trans_paragraphs[i].strip()
            if orig and trans and orig != trans:
                # Simple string replacement (first occurrence only)
                content = content.replace(orig, trans, 1)
        
        return content.encode('utf-8')

    def _apply_to_html(self, html_bytes, orig_paragraphs, trans_paragraphs):
        """
        Apply translations to HTML files.
        
        CRITICAL: Preserves the XML declaration and original document structure.
        Uses sequential index-based matching to handle duplicate text correctly.
        """
        raw = html_bytes.decode('utf-8')
        
        # 1. Save the XML declaration if present (BeautifulSoup strips it)
        xml_decl = ""
        xml_match = re.match(r'(<\?xml[^?]*\?>)\s*', raw)
        if xml_match:
            xml_decl = xml_match.group(1) + "\n"
        
        # 2. Parse with html.parser
        soup = BeautifulSoup(raw, 'html.parser')
        
        # 3. Build text->translation map (with queue for duplicates)
        text_map = {}
        count = min(len(orig_paragraphs), len(trans_paragraphs))
        print(f"DEBUG: Applying translation (orig={len(orig_paragraphs)}, trans={len(trans_paragraphs)})")
        
        for i in range(count):
            orig = orig_paragraphs[i].strip()
            trans = trans_paragraphs[i].strip()
            if orig and trans:
                if orig not in text_map:
                    text_map[orig] = []
                text_map[orig].append(trans)
        
        # 4. Replace <title> tag first (index 0 in orig_paragraphs is title if extracted)
        title_tag = soup.find('title')
        if title_tag:
            title_text = title_tag.get_text().strip()
            if title_text in text_map and text_map[title_text]:
                title_tag.string = text_map[title_text].pop(0)
        
        # 5. Replace block-level tags sequentially
        matched_count = 0
        for tag in soup.find_all(self.TRANSLATABLE_TAGS):
            # Same logic as extraction: skip parent blocks that contain links
            if tag.name != 'a' and tag.find('a'):
                continue

            if tag.find(['img', 'image', 'svg', 'table', 'pre', 'code']):
                continue
            
            tag_text = tag.get_text().strip()
            if tag_text in text_map and text_map[tag_text]:
                trans = text_map[tag_text].pop(0)
                tag.clear()
                tag.string = trans
                matched_count += 1
        
        print(f"DEBUG: Successfully replaced {matched_count} tags")
        
        # 6. Serialize and restore XML declaration
        result = str(soup)
        # Strip any XML declaration BeautifulSoup may have kept
        result = re.sub(r'^<\?xml[^?]*\?>\s*', '', result)
        return (xml_decl + result).encode('utf-8')
