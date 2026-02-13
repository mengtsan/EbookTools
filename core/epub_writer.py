from ebooklib import epub
import os

class EpubWriter:
    def __init__(self, filename):
        self.filename = filename
        self.book = epub.EpubBook()
        self.chapters = []

    def set_metadata(self, title, language='en', author='CosyAudiobook'):
        self.book.set_identifier(str(os.path.basename(self.filename)))
        self.book.set_title(title)
        self.book.set_language(language)
        self.book.add_author(author)

    def add_chapter(self, title, text):
        # Create chapter
        chapter_file_name = f'chap_{len(self.chapters) + 1}.xhtml'
        c = epub.EpubHtml(title=title, file_name=chapter_file_name, lang='hr')
        
        # Convert text newlines to HTML paragraphs
        # Simple conversion: split by double newlines for paragraphs
        paragraphs = text.split('\n\n')
        html_content = f"<h1>{title}</h1>"
        for i, p in enumerate(paragraphs):
            # Dedup: If first paragraph is identical to title, skip it
            if i == 0 and p.strip() == title.strip():
                continue
                
            if p.strip():
                html_content += f"<p>{p.strip().replace(chr(10), '<br/>')}</p>"
        
        c.content = html_content
        self.book.add_item(c)
        self.chapters.append(c)

    def write(self):
        # detailed table of contents
        self.book.toc = self.chapters

        # add default NCX and Nav file
        self.book.add_item(epub.EpubNcx())
        self.book.add_item(epub.EpubNav())

        # define CSS style
        style = 'body { font-family: Times, Times New Roman, serif; }'
        nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)
        self.book.add_item(nav_css)

        # basic spine
        self.book.spine = ['nav'] + self.chapters

        # write to file
        epub.write_epub(self.filename, self.book, {})
