from bs4 import BeautifulSoup

TRANSLATABLE_TAGS = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'a']

html = """
<html>
<body>
  <h1>Table of Contents</h1>
  <p class="toc-item"><a href="chapter1.html">Chapter One</a></p>
  <p class="toc-item"><a href="chapter2.html">Chapter Two</a></p>
  <p>Read <a href="ref.html">Reference</a> please.</p>
</body>
</html>
"""

soup = BeautifulSoup(html, 'html.parser')

print("=== EXTRACTION ===")
extracted = []
for tag in soup.find_all(TRANSLATABLE_TAGS):
    # Logic from epub_processor.py
    if tag.name != 'a' and tag.find('a'):
        print(f"Skipping parent block: <{tag.name}> containing links")
        continue

    text = tag.get_text().strip()
    if text:
        extracted.append(text)
        print(f"Extracted ({tag.name}): {text}")

print("\n=== APPLICATION ===")
# Mock translations
translations = {
    "Table of Contents": "目錄",
    "Chapter One": "第一章",
    "Chapter Two": "第二章",
    "Reference": "參考資料"
}

# Logic from _apply_to_html
text_map = {}
for orig, trans in translations.items():
    if orig not in text_map: text_map[orig] = []
    text_map[orig].append(trans)

for tag in soup.find_all(TRANSLATABLE_TAGS):
    if tag.name != 'a' and tag.find('a'):
        continue
    
    tag_text = tag.get_text().strip()
    if tag_text in text_map and text_map[tag_text]:
        trans = text_map[tag_text].pop(0)
        tag.clear() # This clears content of the TAG being processed
        tag.string = trans
        print(f"Replaced <{tag.name}>: {trans}")

print("\n=== RESULT HTML ===")
print(str(soup))
