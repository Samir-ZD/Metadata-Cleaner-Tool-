# Metadata Cleaner Tool

A lightweight desktop application for **inspecting, analyzing, and removing metadata from image files**.

Images can contain hidden information such as GPS coordinates, camera details, timestamps, author information, software, comments, thumbnails, and other embedded metadata.

**Metadata Cleaner Tool** lets you inspect this information, identify potentially sensitive data, and create a clean copy of the image.

The application works locally on your computer. Images are not uploaded to a server.

## Features

* Analyze image metadata
* Display actual metadata values
* Privacy-focused metadata analysis
* Risk classification: Critical, High, Medium, Technical
* GPS/location detection
* Camera and device information detection
* Personal/author information detection
* Date and time detection
* Description, title, keyword and comment detection
* EXIF, IPTC and XMP inspection
* PNG, WebP, HEIC/HEIF and TIFF metadata inspection
* Camera and RAW metadata support through ExifTool
* Embedded thumbnail and preview detection
* Search metadata fields
* Filter metadata by category
* Hide fields that are not present
* Export complete metadata information to JSON
* Create sanitized copies of images
* Optional source-file overwrite
* Automatic backup before overwrite
* SHA-256 integrity hashes
* Independent post-sanitization verification
* Before/after metadata comparison
* Image dimension and pixel comparison
* Operation and verification logs
* Optional drag-and-drop support

## Supported Formats

* JPG / JPEG
* PNG
* WebP
* TIFF / TIF
* HEIC / HEIF
* CR2 / CR3
* NEF
* ARW
* RAF
* RW2
* ORF
* DNG
* SRW
* PEF

RAW and HEIC/HEIF files work best with ExifTool installed.

## Installation

### Requirements

* Python 3.10+
* Pillow
* Optional: tkinterdnd2
* Recommended: ExifTool

Install Python dependencies:

```bash
python -m pip install Pillow tkinterdnd2
```

If drag-and-drop is not needed, `tkinterdnd2` can be omitted.

### Run

```bash
python image_metadata_sanitizer_tkinter.py
```

## ExifTool

ExifTool is recommended for maximum metadata coverage and verification.

Download it from the official website:

https://exiftool.org/

Make sure `exiftool` is available on your PATH, or use the **ExifTool** button in the application to select the executable manually.

The application also handles the Windows `exiftool(-k).exe` filename automatically when selected through the browser.

## Build as a Desktop App

You can package Metadata Cleaner Tool as a standalone Windows `.exe` so users do not need to run Python manually.

### 1. Install PyInstaller

```bash
python -m pip install pyinstaller
```

### 2. Build the application

From the project folder:

```bash
pyinstaller --noconsole --onefile --name "Metadata Cleaner Tool" image_metadata_sanitizer_tkinter.py
```

The finished executable will be created in:

```text
dist/Metadata Cleaner Tool.exe
```

You can then distribute that `.exe` as the desktop application.

### 3. ExifTool

ExifTool is a separate dependency. For full metadata support, users should have ExifTool installed or provide the executable through the application's **ExifTool** button.

If you want to distribute ExifTool together with your application, check its licensing and redistribution requirements before bundling it.

## How It Works

1. Open an image.
2. Review detected metadata and privacy information.
3. Inspect fields if needed.
4. Click **Maximum Sanitize**.
5. Create a clean copy.
6. The application verifies the resulting file.
7. Review the before/after results.

Original images are not modified by default.

## Safe Sanitization

* Creates a separate output file
* Does not silently overwrite existing files
* Uses temporary files during processing
* Verifies the generated image
* Calculates SHA-256 hashes
* Checks source-file integrity
* Cleans temporary files
* Creates a verified backup before an explicitly enabled overwrite

## Verification

The application reports:

* Metadata before/after
* Removed/changed/preserved/added fields
* Unexpected metadata
* Remaining metadata
* Image dimensions
* Pixel comparison
* SHA-256 hashes
* Verification status

## Metadata JSON Export

Exports:

* Metadata field
* Actual value
* Risk level
* Category
* Present/not present status
* Image information
* Metadata summary

## Privacy

Metadata Cleaner Tool helps identify and remove information that may reveal details about an image or its creator.

Metadata removal does not make an image completely anonymous. Visible information such as faces, documents, signs, locations, or license plates remains part of the image.

## Technology

* Python
* Tkinter
* Pillow
* ExifTool
* tkinterdnd2
* PyInstaller

## License

This project is licensed under the **MIT License**.

See the [LICENSE](LICENSE) file for details.

## Disclaimer

No metadata-cleaning tool can guarantee removal of every possible piece of information from every image format.

Always verify the resulting file before sharing sensitive material.
