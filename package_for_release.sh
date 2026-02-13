#!/bin/bash

# Output filename
OUTPUT_NAME="CosyAudiobook_Mac_Portable.zip"
TEMP_DIR="CosyAudiobook_Dist"

echo "Cleaning up old builds..."
rm -rf "$TEMP_DIR"
rm -f "$OUTPUT_NAME"

echo "Creating staging directory..."
mkdir "$TEMP_DIR"

# Copy essential files
echo "Copying files..."
cp app.py "$TEMP_DIR/"
cp requirements.txt "$TEMP_DIR/"
cp requirements_cosy.txt "$TEMP_DIR/"
cp start_app.command "$TEMP_DIR/"
cp README_USER.md "$TEMP_DIR/" 2>/dev/null || echo "Warning: README_USER.md not found (creating empty one later if needed)"

# Copy directories
cp -r core "$TEMP_DIR/"
cp -r static "$TEMP_DIR/"
cp -r voices "$TEMP_DIR/"

# Create empty directories
mkdir -p "$TEMP_DIR/uploads"
mkdir -p "$TEMP_DIR/output"
mkdir -p "$TEMP_DIR/translations"

# Clean up inside staging (e.g. remove __pycache__)
find "$TEMP_DIR" -type d -name "__pycache__" -exec rm -rf {} +
find "$TEMP_DIR" -type f -name ".DS_Store" -delete

# Permission
chmod +x "$TEMP_DIR/start_app.command"

echo "Zipping..."
zip -r "$OUTPUT_NAME" "$TEMP_DIR"

echo "Cleaning up..."
rm -rf "$TEMP_DIR"

echo "=========================================="
echo "Packaged successfully: $OUTPUT_NAME"
echo "You can now send this zip file to other Mac users."
echo "=========================================="
