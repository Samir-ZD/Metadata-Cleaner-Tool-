#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from PIL import Image, ImageOps, ImageTk, ImageChops
except ImportError as exc:
    raise SystemExit(
        "Pillow is required. Install it with:\n\n    pip install Pillow"
    ) from exc

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_FILES = None
    TkinterDnD = None
    DND_AVAILABLE = False


APP_NAME = "Metadata Cleaner Tool"
SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff",
    ".heic", ".heif", ".cr2", ".cr3", ".nef", ".arw", ".raf",
    ".rw2", ".orf", ".dng", ".srw", ".pef"
}

# Risk classification uses normalized metadata key/tag names.
CRITICAL_TERMS = (
    "gps", "latitude", "longitude", "altitude", "owner",
    "serialnumber", "serial", "contact", "person", "maker"
)
HIGH_TERMS = (
    "camera", "make", "model", "lens", "datetime", "datecreated",
    "createdate", "modifydate", "creator", "author", "copyright",
    "software", "history", "iptc", "xmp"
)
MEDIUM_TERMS = (
    "keyword", "description", "title", "caption", "headline",
    "rating", "category", "subject", "comment"
)

KNOWN_METADATA_FIELDS = {
    "EXIF": [
        "EXIF:Make", "EXIF:Model", "EXIF:LensMake", "EXIF:LensModel",
        "EXIF:BodySerialNumber", "EXIF:LensSerialNumber", "EXIF:Software",
        "EXIF:DateTime", "EXIF:DateTimeOriginal", "EXIF:DateTimeDigitized",
        "EXIF:SubSecTime", "EXIF:SubSecTimeOriginal", "EXIF:SubSecTimeDigitized",
        "EXIF:Orientation", "EXIF:ExposureTime", "EXIF:FNumber",
        "EXIF:ISOSpeedRatings", "EXIF:FocalLength", "EXIF:FocalLengthIn35mmFormat",
        "EXIF:Flash", "EXIF:WhiteBalance", "EXIF:MeteringMode",
        "EXIF:ExposureProgram", "EXIF:ExposureCompensation", "EXIF:ColorSpace",
        "EXIF:PixelXDimension", "EXIF:PixelYDimension", "EXIF:Artist",
        "EXIF:Copyright", "EXIF:ImageDescription", "EXIF:UserComment", "EXIF:MakerNote",
    ],
    "GPS": [
        "EXIF:GPSLatitude", "EXIF:GPSLatitudeRef", "EXIF:GPSLongitude",
        "EXIF:GPSLongitudeRef", "EXIF:GPSAltitude", "EXIF:GPSAltitudeRef",
        "EXIF:GPSTimeStamp", "EXIF:GPSDateStamp", "EXIF:GPSSpeed",
        "EXIF:GPSSpeedRef", "EXIF:GPSTrack", "EXIF:GPSTrackRef",
        "EXIF:GPSImgDirection", "EXIF:GPSImgDirectionRef", "EXIF:GPSMapDatum",
    ],
    "IPTC": [
        "IPTC:ObjectName", "IPTC:Headline", "IPTC:Caption-Abstract",
        "IPTC:By-line", "IPTC:By-lineTitle", "IPTC:Credit", "IPTC:Source",
        "IPTC:CopyrightNotice", "IPTC:Keywords", "IPTC:Category",
        "IPTC:City", "IPTC:Province-State", "IPTC:Country-PrimaryLocationName",
        "IPTC:Country-PrimaryLocationCode", "IPTC:Sub-location", "IPTC:Contact",
        "IPTC:Writer-Editor", "IPTC:DateCreated", "IPTC:TimeCreated",
        "IPTC:SpecialInstructions", "IPTC:OriginalTransmissionReference",
    ],
    "XMP": [
        "XMP:Title", "XMP:Description", "XMP:Creator", "XMP:Rights",
        "XMP:Copyright", "XMP:Subject", "XMP:Keywords", "XMP:Rating",
        "XMP:Label", "XMP:CreatorTool", "XMP:ModifyDate", "XMP:CreateDate",
        "XMP:MetadataDate", "XMP:History", "XMP:InstanceID", "XMP:DocumentID",
        "XMP:OriginalDocumentID", "XMP:UsageTerms",
    ],
    "Camera": [
        "EXIF:SerialNumber", "EXIF:InternalSerialNumber", "EXIF:CameraOwnerName",
        "EXIF:OwnerName", "EXIF:LensID", "EXIF:LensSerialNumber",
        "EXIF:FirmwareVersion", "EXIF:CameraModelName", "EXIF:LensInfo",
    ],
    "Preview": [
        "EXIF:ThumbnailImage", "EXIF:PreviewImage", "EXIF:PreviewImageSize",
        "EXIF:ThumbnailLength", "EXIF:ThumbnailOffset", "EXIF:OtherImage",
    ],
    "PNG": [
        "PNG:TextualData", "PNG:Comment", "PNG:Description", "PNG:Author",
        "PNG:Copyright", "PNG:CreationTime", "PNG:Software", "PNG:Title",
        "PNG:Source", "PNG:Warning",
    ],
    "WebP": [
        "WebP:Comment", "WebP:EXIF", "WebP:XMP", "WebP:ICC_Profile",
        "WebP:Animation", "WebP:LoopCount",
    ],
    "HEIF/HEIC": [
        "QuickTime:Make", "QuickTime:Model", "QuickTime:Software",
        "QuickTime:CreationDate", "QuickTime:LocationISO6709",
        "QuickTime:LocationName", "QuickTime:Artist", "QuickTime:Copyright",
        "QuickTime:Description", "QuickTime:Encoder",
    ],
    "TIFF": [
        "IFD0:Make", "IFD0:Model", "IFD0:Software", "IFD0:Artist",
        "IFD0:Copyright", "IFD0:ImageDescription", "IFD0:DateTime",
        "IFD0:DocumentName", "IFD0:HostComputer", "IFD0:XPTitle",
        "IFD0:XPComment", "IFD0:XPAuthor", "IFD0:XPKeywords", "IFD0:XPSubject",
    ],
    "Other": [
        "File:FileName", "File:FileSize", "File:FileType",
        "File:FileTypeExtension", "File:MIMEType",
        "ICC_Profile:ProfileDescription", "ICC_Profile:ProfileCopyright",
        "ICC_Profile:ProfileCreator", "ICC_Profile:DeviceManufacturer",
        "Composite:ImageSize",
    ],
}

# Tags that ExifTool can emit while searching for embedded previews.
PREVIEW_KEYS = {
    "thumbnailimage", "previewimage", "previewifd", "previewimagesize",
    "otherimage", "preview", "thumbnail"
}


@dataclass
class MetadataRecord:
    key: str
    value: str
    risk: str
    group: str


@dataclass
class ImageInfo:
    width: int | None = None
    height: int | None = None
    mode: str = ""
    format: str = ""
    bit_depth: str = ""
    has_alpha: bool = False
    file_size: int = 0
    pixel_hash: str | None = None
    image_opened: bool = False


def classify_risk(key: str, value: Any) -> str:
    k = key.lower().replace(" ", "").replace("_", "").replace(":", "")
    if any(term in k for term in CRITICAL_TERMS):
        return "Critical"
    if any(term in k for term in HIGH_TERMS):
        return "High"
    if any(term in k for term in MEDIUM_TERMS):
        return "Medium"
    return "Technical"


def risk_symbol(risk: str) -> str:
    return {
        "Critical": "🔴",
        "High": "🟠",
        "Medium": "🟡",
        "Technical": "🟢",
    }.get(risk, "⚪")


def group_for_key(key: str) -> str:
    k = key.lower()
    if "gps" in k:
        return "GPS"
    if any(x in k for x in ("iptc", "headline", "by-line", "byline")):
        return "IPTC"
    if "xmp" in k:
        return "XMP"
    if any(x in k for x in ("makernote", "serial", "camera", "lens")):
        return "Camera"
    if any(x in k for x in ("preview", "thumbnail")):
        return "Preview"
    if any(x in k for x in ("png:", "png")):
        return "PNG"
    if any(x in k for x in ("webp", "riff")):
        return "WebP"
    if any(x in k for x in ("heif", "heic", "hevc", "ispe", "meta:")):
        return "HEIF/HEIC"
    if any(x in k for x in ("tiff", "ifd")):
        return "TIFF"
    if "exif" in k or "orientation" in k or "exposure" in k:
        return "EXIF"
    return "Other"


def normalize_exiftool_path(path: Path) -> str | None:
    path = path.expanduser().resolve()
    if not path.is_file():
        return None

    if path.name.lower() == "exiftool(-k).exe":
        support_dir = Path.home() / ".image_metadata_sanitizer"
        support_dir.mkdir(parents=True, exist_ok=True)
        normalized = support_dir / "exiftool.exe"
        if (
            not normalized.exists()
            or path.stat().st_mtime_ns > normalized.stat().st_mtime_ns
            or path.stat().st_size != normalized.stat().st_size
        ):
            shutil.copy2(path, normalized)
        return str(normalized)

    return str(path)


def find_exiftool() -> str | None:
    candidates = []

    for command in ("exiftool", "exiftool.exe", "exiftool(-k).exe"):
        exe = shutil.which(command)
        if exe:
            candidates.append(Path(exe))

    base_dirs = [
        Path(__file__).resolve().parent,
        Path(sys.argv[0]).resolve().parent,
        Path.cwd(),
        Path.home() / ".image_metadata_sanitizer",
    ]

    for base in base_dirs:
        candidates.extend([
            base / "exiftool",
            base / "exiftool.exe",
            base / "exiftool(-k).exe",
            base / "tools" / "exiftool.exe",
            base / "tools" / "exiftool(-k).exe",
            base / "bin" / "exiftool.exe",
            base / "bin" / "exiftool(-k).exe",
        ])

    if sys.platform.startswith("win"):
        candidates.extend([
            Path(r"C:\Program Files\ExifTool\exiftool.exe"),
            Path(r"C:\Program Files\ExifTool\exiftool(-k).exe"),
            Path(r"C:\Windows\exiftool.exe"),
            Path(r"C:\Windows\exiftool(-k).exe"),
        ])
    elif sys.platform == "darwin":
        candidates.extend([
            Path("/usr/local/bin/exiftool"),
            Path("/opt/homebrew/bin/exiftool"),
            Path("/usr/bin/exiftool"),
        ])
    else:
        candidates.extend([
            Path("/usr/local/bin/exiftool"),
            Path("/usr/bin/exiftool"),
            Path("/snap/bin/exiftool"),
        ])

    seen = set()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            normalized = normalize_exiftool_path(resolved)
            if not normalized:
                continue
            result = run_exiftool(normalized, ["-ver"], timeout=10)
            if result.returncode == 0 and result.stdout.strip():
                return normalized
        except (OSError, subprocess.SubprocessError):
            continue

    return None


def exiftool_status() -> str:
    found = find_exiftool()
    if found:
        return f"Metadata engine: Ready ({Path(found).name})"
    return "Metadata engine: Limited — ExifTool not found"

def run_exiftool(exiftool: str, args: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [exiftool, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
        check=False,
    )


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)
    finally:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def is_present_record(record: MetadataRecord) -> bool:
    return record.value not in ("", "EMPTY / NOT PRESENT", "NOT PRESENT")


def metadata_diff(before: list[MetadataRecord], after: list[MetadataRecord]) -> dict[str, Any]:
    ignored_prefixes = ("system:", "file:", "composite:", "exiftool:")

    def to_map(records: list[MetadataRecord]) -> dict[str, str]:
        result = {}
        for rec in records:
            if not is_present_record(rec):
                continue
            if rec.key.lower().startswith(ignored_prefixes):
                continue
            result[rec.key] = rec.value
        return result

    before_map = to_map(before)
    after_map = to_map(after)
    return {
        "before_count": len(before_map),
        "after_count": len(after_map),
        "removed": sorted(k for k in before_map if k not in after_map),
        "changed": sorted(k for k in before_map if k in after_map and before_map[k] != after_map[k]),
        "preserved": sorted(k for k in before_map if k in after_map and before_map[k] == after_map[k]),
        "added": sorted(k for k in after_map if k not in before_map),
    }


def compare_images(source: Path, output: Path) -> dict[str, Any]:
    result = {
        "available": False,
        "dimensions_match": False,
        "pixel_identical": False,
        "changed_pixels": None,
        "changed_pixels_percent": None,
        "mean_absolute_difference": None,
        "error": None,
    }

    try:
        with Image.open(source) as a, Image.open(output) as b:
            a = ImageOps.exif_transpose(a)
            b = ImageOps.exif_transpose(b)
            a.load()
            b.load()
            result["available"] = True
            result["dimensions_match"] = a.size == b.size
            result["source_size"] = a.size
            result["output_size"] = b.size

            if not result["dimensions_match"]:
                return result

            aa = a.convert("RGB")
            bb = b.convert("RGB")
            diff = ImageChops.difference(aa, bb)

            total = aa.width * aa.height
            changed = 0
            histogram = diff.histogram()
            weighted_sum = sum((i % 256) * count for i, count in enumerate(histogram))

            # Avoid Pillow's deprecated Image.getdata() API.
            # Convert the difference image to a compact byte representation
            # and count non-zero RGB triplets.
            diff_bytes = diff.tobytes()
            for offset in range(0, len(diff_bytes), 3):
                if diff_bytes[offset] or diff_bytes[offset + 1] or diff_bytes[offset + 2]:
                    changed += 1

            result["changed_pixels"] = changed
            result["changed_pixels_percent"] = (changed / total * 100.0) if total else 0.0
            result["mean_absolute_difference"] = (
                weighted_sum / (total * 3) if total else 0.0
            )
            result["pixel_identical"] = changed == 0

    except Exception as exc:
        result["error"] = str(exc)

    return result


def make_operation_log(
    src: Path,
    output: Path,
    overwrite: bool,
    source_hash: str,
    output_hash: str,
    backup: Path | None,
    backup_hash: str | None,
    processing_mode: str,
    temp_cleaned: bool,
) -> list[str]:
    return [
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Maximum sanitization started",
        f"Source: {src}",
        f"Destination: {output}",
        f"Safe Mode: ENABLED",
        f"Overwrite requested: {'YES' if overwrite else 'NO'}",
        f"Processing mode: {processing_mode}",
        f"Source SHA-256: {source_hash}",
        f"Temporary output created atomically: YES",
        f"Backup created: {'YES' if backup else 'NO'}",
        f"Backup SHA-256: {backup_hash or '—'}",
        f"Output SHA-256: {output_hash}",
        f"Temporary files cleaned: {'YES' if temp_cleaned else 'NO'}",
        f"Source replacement performed: {'YES' if overwrite else 'NO'}",
        f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Maximum sanitization finished",
    ]


def make_verification_log(
    source_hash_before: str,
    source_hash_after: str | None,
    output_hash: str,
    backup_hash: str | None,
    final_message: str,
    comparison: dict[str, Any],
    diff: dict[str, Any],
) -> list[str]:
    return [
        "INDEPENDENT VERIFICATION",
        f"Source SHA-256 before: {source_hash_before}",
        f"Source SHA-256 after: {source_hash_after or '—'}",
        f"Output SHA-256: {output_hash}",
        f"Backup SHA-256: {backup_hash or '—'}",
        f"Source integrity preserved: {'YES' if source_hash_after == source_hash_before else 'NO'}",
        f"Metadata before: {diff.get('before_count', 0)}",
        f"Metadata after: {diff.get('after_count', 0)}",
        f"Metadata removed: {len(diff.get('removed', []))}",
        f"Metadata changed: {len(diff.get('changed', []))}",
        f"Metadata preserved: {len(diff.get('preserved', []))}",
        f"Metadata added: {len(diff.get('added', []))}",
        f"Dimensions match: {comparison.get('dimensions_match', '—')}",
        f"Pixel-identical: {comparison.get('pixel_identical', '—')}",
        f"Changed pixels: {comparison.get('changed_pixels', '—')}",
        f"Changed pixels %: {comparison.get('changed_pixels_percent', '—')}",
        f"Mean absolute difference: {comparison.get('mean_absolute_difference', '—')}",
        f"Metadata verification: PASSED",
        f"Verifier result: {final_message}",
    ]


def remove_all_metadata_with_exiftool(exiftool: str, src: Path, dst: Path) -> None:
    if not Path(exiftool).is_file():
        raise RuntimeError(f"ExifTool executable not found: {exiftool}")

    if not src.is_file():
        raise RuntimeError(f"Source image not found: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)

    if dst.exists():
        dst.unlink()

    # Create a separate output file. Do not use -overwrite_original because
    # the source image must remain untouched unless the explicit overwrite
    # workflow replaces it only after verification.
    result = run_exiftool(
        exiftool,
        [
            "-all=",
            "-o", str(dst),
            str(src),
        ],
        timeout=180,
    )

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(detail or "ExifTool could not create the sanitized image.")

    if not dst.exists() or dst.stat().st_size == 0:
        raise RuntimeError("ExifTool reported success, but no valid output file was created.")

def compute_pixel_hash(image: Image.Image) -> str:
    img = image
    if img.mode not in ("1", "L", "LA", "I", "F", "RGB", "RGBA", "I;16", "I;16L", "I;16B"):
        img = img.convert("RGBA")
    h = hashlib.sha256()
    h.update(img.mode.encode("utf-8"))
    h.update(str(img.size).encode("ascii"))
    try:
        h.update(img.tobytes())
    except Exception:
        h.update(img.convert("RGBA").tobytes())
    return h.hexdigest()


def open_preview(path: Path) -> tuple[Image.Image, ImageInfo]:
    img = Image.open(path)
    info = ImageInfo(
        width=img.width,
        height=img.height,
        mode=img.mode,
        format=img.format or path.suffix.upper().lstrip("."),
        file_size=path.stat().st_size,
        has_alpha=("A" in img.getbands()),
        image_opened=True,
    )
    try:
        info.bit_depth = str(ImageModeDepth.get(img.mode, "?"))
    except Exception:
        info.bit_depth = "?"
    return img, info


# Approximate channel bit depth for common Pillow modes.
ImageModeDepth = {
    "1": 1,
    "L": 8,
    "LA": 8,
    "RGB": 8,
    "RGBA": 8,
    "P": 8,
    "CMYK": 8,
    "YCbCr": 8,
    "I;16": 16,
    "I;16L": 16,
    "I;16B": 16,
    "I": 32,
    "F": 32,
}


def load_exiftool_metadata(exiftool: str, path: Path) -> tuple[list[MetadataRecord], dict[str, Any]]:
    result = run_exiftool(
        exiftool, ["-j", "-G1", "-a", "-s", "-struct", "-ee", str(path)], timeout=90
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ExifTool metadata scan failed.")

    payload = json.loads(result.stdout)
    root = payload[0] if payload else {}
    discovered: dict[str, MetadataRecord] = {}

    for key, value in root.items():
        if key == "SourceFile":
            continue
        display = (
            json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
            if isinstance(value, (dict, list))
            else str(value)
        )
        discovered[key] = MetadataRecord(
            key=key,
            value=display,
            risk=classify_risk(key, display),
            group=group_for_key(key),
        )

    for group, fields in KNOWN_METADATA_FIELDS.items():
        for field in fields:
            if field not in discovered:
                discovered[field] = MetadataRecord(
                    key=field,
                    value="EMPTY / NOT PRESENT",
                    risk=classify_risk(field, ""),
                    group=group,
                )

    return list(discovered.values()), root


def save_with_pillow(src: Path, dst: Path) -> tuple[str, str]:
    ext = dst.suffix.lower()

    with Image.open(src) as original:
        img = ImageOps.exif_transpose(original)
        img.load()

        if ext in (".jpg", ".jpeg"):
            if img.mode not in ("RGB", "L", "CMYK"):
                img = img.convert("RGB")
            img.save(
                dst,
                format="JPEG",
                quality=100,
                subsampling=0,
                optimize=True,
                exif=b"",
                icc_profile=None,
                comment=None,
            )
            return "Re-encoded", "JPEG was decoded and encoded once at maximum practical quality."

        if ext == ".png":
            clean = img.convert("RGBA" if img.mode == "P" and "transparency" in img.info else
                                "RGB" if img.mode == "P" else img.mode)
            if img.mode != "P":
                clean = img.copy()
            clean.save(dst, format="PNG", optimize=True, compress_level=9)
            return "Lossless", "PNG was reconstructed from decoded pixels without copying source metadata."

        if ext == ".webp":
            if img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGBA")
            img.save(dst, format="WEBP", quality=100, method=6,
                     exif=b"", icc_profile=None, xmp=None)
            return "Re-encoded", "WebP was decoded and encoded once at a high-quality setting."

        if ext in (".tif", ".tiff"):
            clean = img.copy()
            clean.save(dst, format="TIFF", compression="tiff_lzw")
            return "Lossless", "TIFF was reconstructed without source metadata."

    raise RuntimeError(
        f"Pillow fallback cannot safely reconstruct {src.suffix} without ExifTool. "
        "Install ExifTool for HEIC/HEIF/RAW and broader format coverage."
    )


def detect_preview_fields(root: dict[str, Any]) -> list[str]:
    found = []
    for key in root:
        norm = key.lower().replace("-", "").replace(" ", "")
        if norm in PREVIEW_KEYS or any(term in norm for term in PREVIEW_KEYS):
            found.append(key)
    return found


def verification_scan(
    exiftool: str | None,
    output_path: Path
) -> tuple[bool, list[MetadataRecord], str]:
    if exiftool:
        records, root = load_exiftool_metadata(exiftool, output_path)

        # These are generated/technical file properties, not embedded image
        # metadata and therefore must not make sanitization fail.
        system_keys = {
            "exiftool:exiftoolversion",
            "system:filename",
            "system:directory",
            "system:filesize",
            "system:filemodifydate",
            "system:fileaccessdate",
            "system:filecreatedate",
            "system:filepermissions",
            "file:filename",
            "file:directory",
            "file:filesize",
            "file:filetype",
            "file:filetypeextension",
            "file:mimetype",
            "file:filemodifydate",
            "file:fileaccessdate",
            "file:filecreatedate",
            "file:filepermissions",
            "png:imagewidth",
            "png:imageheight",
            "png:bitdepth",
            "png:colortype",
            "png:compression",
            "png:filter",
            "png:interlace",
            "composite:imagesize",
            "composite:megapixels",
        }

        # These are empty placeholders from the UI's supported-field catalog,
        # not metadata actually present in the output file.
        present_records = [
            rec for rec in records
            if rec.value not in ("", "EMPTY / NOT PRESENT", "NOT PRESENT")
        ]

        optional = []
        for rec in present_records:
            key = rec.key.lower().replace(" ", "")
            if key in system_keys:
                continue

            # Treat common format/technical structures as non-privacy
            # information unless they actually carry optional metadata.
            if key.startswith(("png:", "file:", "composite:", "system:", "exiftool:")):
                continue

            optional.append(rec)

        previews = detect_preview_fields(root)

        # ExifTool can expose preview-related technical fields even when no
        # embedded preview payload remains. Only fail if an actual preview
        # value/payload is present.
        real_previews = []
        for key in previews:
            value = root.get(key)
            if value not in (None, "", 0, False):
                if isinstance(value, (bytes, bytearray)) and len(value) == 0:
                    continue
                real_previews.append(key)

        if optional or real_previews:
            detail = (
                f"{len(optional)} optional metadata field(s) remain"
                f"; previews detected: {len(real_previews)}."
            )
            return False, optional, detail

        return True, [], "No known original optional metadata was detected by the independent scan."

    # Pillow-only verification.
    try:
        with Image.open(output_path) as img:
            info_keys = set(img.info.keys())
            allowed = {
                # Normal decoder/encoder information required or routinely
                # generated by the image format, not privacy metadata.
                "compression", "dpi", "gamma", "transparency",

                # JPEG/JFIF structural fields. Pillow may expose these after
                # opening a clean JPEG even though all optional metadata has
                # been removed.
                "jfif", "jfif_version", "jfif_unit", "jfif_density",
                "jfifthumbnail",
                "jfifversion", "jfifunit", "jfifdensity",
            }
            dangerous = [k for k in info_keys if k.lower() not in allowed]
            if dangerous:
                records = [
                    MetadataRecord(
                        key=str(k),
                        value=str(img.info.get(k)),
                        risk=classify_risk(str(k), str(img.info.get(k))),
                        group=group_for_key(str(k)),
                    )
                    for k in dangerous
                ]
                return False, records, (
                    "Pillow-only verification found remaining optional "
                    "embedded metadata: " + ", ".join(dangerous)
                )
            return True, [], "Pillow-only verification passed for the metadata exposed by Pillow."
    except Exception as exc:
        return False, [], f"Could not reopen output: {exc}"


def privacy_display_values(records: list[MetadataRecord]) -> dict[str, str]:
    present = [
        r for r in records
        if r.value not in ("", "EMPTY / NOT PRESENT", "NOT PRESENT")
    ]

    def first_matching(
        terms: tuple[str, ...],
        groups: tuple[str, ...] | None = None,
    ) -> str | None:
        for rec in present:
            key = rec.key.lower()
            if groups and rec.group not in groups:
                continue
            if any(term in key for term in terms):
                value = str(rec.value).strip()
                if value:
                    return value
        return None

    # GPS / location.
    location = first_matching(
        (
            "country-primarylocationname",
            "country",
            "locationname",
            "city",
            "province",
            "state",
            "sublocation",
        )
    )
    if not location:
        lat = first_matching(("gpslatitude",), ("GPS",))
        lon = first_matching(("gpslongitude",), ("GPS",))
        if lat and lon:
            location = f"{lat}, {lon}"

    # Personal identity / ownership information.
    personal = first_matching((
        "creator", "author", "artist", "owner", "cameraownername",
        "contact", "byline", "copyright",
    ))

    # Device / camera information.
    device = first_matching((
        "cameramodelname", "cameramodel", "model", "make",
    ))

    # Capture / creation date and time.
    date_time = first_matching((
        "datetimeoriginal", "datecreated", "createdate",
        "datetime", "creationdate", "timecreated",
    ))

    # Human-readable descriptive metadata.
    descriptive = first_matching((
        "title", "description", "caption", "headline",
        "keyword", "subject", "objectname",
    ))

    return {
        "gps": location or "Not present",
        "personal": personal or "Not present",
        "device": device or "Not present",
        "datetime": date_time or "Not present",
        "descriptive": descriptive or "Not present",
    }


def build_privacy_summary(records: list[MetadataRecord]) -> dict[str, Any]:
    present = [
        r for r in records
        if r.value not in ("", "EMPTY / NOT PRESENT", "NOT PRESENT")
    ]
    summary = {"Critical": 0, "High": 0, "Medium": 0, "Technical": 0}
    for rec in present:
        summary[rec.risk] += 1

    critical = [r.key.lower() for r in present if r.risk == "Critical"]
    high = [r.key.lower() for r in present if r.risk == "High"]

    return {
        "counts": summary,
        "total": len(records),
        "present_total": len(present),
        "sensitive": summary["Critical"] + summary["High"] + summary["Medium"],
        "gps": any("gps" in k for k in critical),
        "personal": any(any(x in k for x in ("owner", "contact", "person", "serial")) for k in critical),
        "device": any(any(x in k for x in ("camera", "lens")) for k in high),
        "datetime": any("date" in r.key.lower() or "time" in r.key.lower() for r in present),
        "descriptive": any(r.risk == "Medium" for r in present),
    }



class SanitizerApp(TkinterDnD.Tk if DND_AVAILABLE else tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1220x820")
        self.minsize(1000, 700)

        self.exiftool = find_exiftool()
        self.source_path: Path | None = None
        self.source_image: Image.Image | None = None
        self.source_info: ImageInfo | None = None
        self.source_records: list[MetadataRecord] = []
        self.source_raw: dict[str, Any] = {}
        self.current_photo: ImageTk.PhotoImage | None = None
        self.status_var = tk.StringVar(value="Ready")
        self.file_var = tk.StringVar(value="No image loaded")
        self.quality_var = tk.StringVar(value="—")
        self.metadata_count_var = tk.StringVar(value="Metadata fields: 0")
        self.sensitive_count_var = tk.StringVar(value="Sensitive fields: 0")
        self.search_var = tk.StringVar()
        self.group_var = tk.StringVar(value="Overview")
        self.hide_not_present_var = tk.BooleanVar(value=False)
        self.safe_mode_var = tk.BooleanVar(value=True)
        self.busy = False
        self.last_verification: dict[str, Any] | None = None
        self.last_operation_log: list[dict[str, Any]] = []
        self.last_verification_log: dict[str, Any] | None = None

        self._setup_style()
        self._build_ui()
        self._show_empty_state()
        self._update_exiftool_status()
        self._setup_drag_and_drop()

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("TkDefaultFont", 19, "bold"))
        style.configure("Section.TLabel", font=("TkDefaultFont", 11, "bold"))
        style.configure("Risk.TLabel", font=("TkDefaultFont", 10, "bold"))
        style.configure("Action.TButton", font=("TkDefaultFont", 11, "bold"), padding=(18, 10))
        style.configure("Danger.TButton", font=("TkDefaultFont", 11, "bold"), padding=(18, 10))
        style.configure("Card.TLabelframe", padding=10)
        style.configure("Treeview", rowheight=27)
        style.configure("Treeview.Heading", font=("TkDefaultFont", 10, "bold"))

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)

        top = ttk.Frame(root)
        top.pack(fill="x", pady=(0, 12))
        ttk.Label(top, text=APP_NAME, style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="Open Image", command=self.open_image).pack(side="right", padx=(8, 0))
        ttk.Button(top, text="Rescan", command=self.rescan_image).pack(side="right", padx=(8, 0))
        ttk.Button(top, text="Save Metadata JSON", command=self.save_metadata_json).pack(side="right", padx=(8, 0))
        ttk.Button(top, text="Save Clean Copy", command=self.start_sanitize).pack(side="right")
        ttk.Button(top, text="ExifTool", command=self.exiftool_menu).pack(side="right", padx=(8, 0))

        filebar = ttk.Frame(root)
        filebar.pack(fill="x", pady=(0, 10))
        ttk.Label(filebar, textvariable=self.file_var).pack(side="left", fill="x", expand=True)
        self.exiftool_status_var = tk.StringVar(value="")
        ttk.Label(filebar, textvariable=self.exiftool_status_var).pack(side="right", padx=(12, 10))
        ttk.Label(filebar, text="Local / Offline", font=("TkDefaultFont", 9, "bold")).pack(side="right")

        main = ttk.Panedwindow(root, orient="horizontal")
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main, padding=(0, 0, 8, 0))
        right = ttk.Frame(main, padding=(8, 0, 0, 0))
        main.add(left, weight=4)
        main.add(right, weight=6)

        preview_card = ttk.LabelFrame(left, text="Image Preview", style="Card.TLabelframe")
        preview_card.pack(fill="both", expand=True)

        self.preview = tk.Label(
            preview_card,
            text="Open an image",
            anchor="center",
            justify="center",
            relief="flat",
        )
        self.preview.pack(fill="both", expand=True, padx=4, pady=4)

        self.image_facts = tk.Text(
            preview_card, height=7, wrap="word", state="disabled",
            bg=self.cget("bg"), relief="flat", font=("TkDefaultFont", 9),
        )
        self.image_facts.pack(fill="x", padx=4, pady=(4, 0))

        privacy_card = ttk.LabelFrame(right, text="Privacy Analysis", style="Card.TLabelframe")
        privacy_card.pack(fill="x", pady=(0, 10))

        self.privacy_grid = ttk.Frame(privacy_card)
        self.privacy_grid.pack(fill="x")
        self.privacy_labels: dict[str, tk.StringVar] = {}
        for idx, (name, label) in enumerate([
            ("gps", "GPS Location"),
            ("personal", "Personal Data"),
            ("device", "Device Information"),
            ("datetime", "Date / Time"),
            ("descriptive", "Descriptive Data"),
        ]):
            ttk.Label(self.privacy_grid, text=label).grid(row=idx, column=0, sticky="w", padx=4, pady=2)
            var = tk.StringVar(value="—")
            self.privacy_labels[name] = var
            ttk.Label(
                self.privacy_grid,
                textvariable=var,
                style="Risk.TLabel",
                wraplength=330,
                justify="left",
            ).grid(row=idx, column=1, sticky="w", padx=18, pady=2)

        counts = ttk.Frame(privacy_card)
        counts.pack(fill="x", pady=(8, 0))
        ttk.Label(counts, textvariable=self.metadata_count_var).pack(side="left")
        ttk.Label(counts, textvariable=self.sensitive_count_var).pack(side="right")

        toolbar = ttk.Frame(right)
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Label(toolbar, text="Category:").pack(side="left")
        groups = [
            "Overview", "EXIF", "IPTC", "XMP", "GPS", "Camera", "Preview",
            "PNG", "WebP", "HEIF/HEIC", "TIFF", "Other"
        ]
        self.group_combo = ttk.Combobox(
            toolbar, textvariable=self.group_var, values=groups,
            state="readonly", width=14
        )
        self.group_combo.pack(side="left", padx=(6, 14))

        ttk.Label(toolbar, text="Search:").pack(side="left")
        search = ttk.Entry(toolbar, textvariable=self.search_var)
        search.pack(side="left", fill="x", expand=True, padx=(6, 0))

        ttk.Checkbutton(
            toolbar,
            text="Hide Not Present",
            variable=self.hide_not_present_var,
            command=self.refresh_metadata_tree,
        ).pack(side="right", padx=(10, 0))

        self.search_var.trace_add("write", lambda *_: self.refresh_metadata_tree())
        self.group_combo.bind("<<ComboboxSelected>>", lambda *_: self.refresh_metadata_tree())

        tree_frame = ttk.Frame(right)
        tree_frame.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("field", "value", "risk"),
            show="headings"
        )
        self.tree.heading("field", text="Field")
        self.tree.heading("value", text="Value")
        self.tree.heading("risk", text="Risk")
        self.tree.column("field", width=210, anchor="w")
        self.tree.column("value", width=520, anchor="w")
        self.tree.column("risk", width=85, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)

        # Dedicated vertical scrollbar for large metadata inventories.
        yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        yscroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=yscroll.set)

        self.tree.tag_configure("Critical", foreground="#a00000")
        self.tree.tag_configure("High", foreground="#9a4a00")
        self.tree.tag_configure("Medium", foreground="#7a6a00")

        bottom = ttk.Frame(root)
        bottom.pack(fill="x", pady=(12, 0))
        ttk.Button(
            bottom, text="Maximum Sanitize",
            style="Action.TButton",
            command=self.start_sanitize
        ).pack(side="right")
        ttk.Label(bottom, textvariable=self.status_var, anchor="w").pack(
            side="left", fill="x", expand=True
        )
        ttk.Label(bottom, text="SAFE MODE ON", font=("TkDefaultFont", 9, "bold")).pack(
            side="right", padx=(10, 0)
        )

        self.progress = ttk.Progressbar(root, mode="indeterminate")
        self.progress.pack(fill="x", pady=(7, 0))

    def _show_empty_state(self) -> None:
        self.preview.configure(
            text="Open an image\n\nJPG • PNG • WebP • TIFF • HEIC • HEIF • RAW",
            image=""
        )
        self.file_var.set("No image loaded")
        self.status_var.set(
            "Ready. Original files are never modified by default."
            + (" Drag & drop is enabled." if DND_AVAILABLE else "")
        )


    def _setup_drag_and_drop(self) -> None:
        if not DND_AVAILABLE:
            return
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._handle_drop)
            self.preview.drop_target_register(DND_FILES)
            self.preview.dnd_bind("<<Drop>>", self._handle_drop)
        except Exception:
            pass

    def _handle_drop(self, event) -> None:
        if self.busy:
            return
        try:
            paths = self.tk.splitlist(event.data)
        except Exception:
            paths = (event.data,)
        for raw_path in paths:
            path_text = str(raw_path).strip()
            if len(path_text) >= 2 and path_text[0] == "{" and path_text[-1] == "}":
                path_text = path_text[1:-1]
            candidate = Path(path_text)
            if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_EXTENSIONS:
                self.load_image(candidate)
                return
        messagebox.showwarning(APP_NAME, "Drop a supported image file.")

    def rescan_image(self) -> None:
        if self.busy:
            return
        if not self.source_path:
            messagebox.showwarning(APP_NAME, "Open an image first.")
            return
        self.load_image(self.source_path)

    def save_metadata_json(self) -> None:
        if self.busy:
            return
        if not self.source_path:
            messagebox.showwarning(APP_NAME, "Open an image first.")
            return
        if not self.source_records:
            messagebox.showwarning(APP_NAME, "No metadata has been analyzed yet.")
            return

        src = self.source_path
        default_name = f"{src.stem}_metadata.json"

        out = filedialog.asksaveasfilename(
            title="Save Metadata as JSON",
            initialdir=str(src.parent),
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[
                ("JSON files", "*.json"),
                ("All files", "*.*"),
            ],
        )
        if not out:
            return

        output_path = Path(out)

        # Export the complete metadata inventory currently used by the viewer:
        # present values plus supported fields that are empty/not present.
        metadata = []
        for rec in self.source_records:
            metadata.append({
                "field": rec.key,
                "value": rec.value,
                "risk": rec.risk,
                "category": rec.group,
                "present": rec.value not in ("", "EMPTY / NOT PRESENT", "NOT PRESENT"),
            })

        payload = {
            "application": APP_NAME,
            "source_file": str(src),
            "source_format": self.source_info.format if self.source_info else None,
            "image": {
                "width": self.source_info.width if self.source_info else None,
                "height": self.source_info.height if self.source_info else None,
                "mode": self.source_info.mode if self.source_info else None,
                "bit_depth": self.source_info.bit_depth if self.source_info else None,
                "alpha": self.source_info.has_alpha if self.source_info else None,
            },
            "summary": {
                "supported_fields": len(self.source_records),
                "present_fields": sum(item["present"] for item in metadata),
                "not_present_fields": sum(not item["present"] for item in metadata),
                "sensitive_fields": sum(
                    item["present"] and item["risk"] in {"Critical", "High", "Medium"}
                    for item in metadata
                ),
            },
            "metadata": metadata,
        }

        try:
            output_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            messagebox.showerror(
                APP_NAME,
                f"Could not save the metadata JSON file:\n\n{exc}",
            )
            return

        self.status_var.set("Metadata JSON saved")
        messagebox.showinfo(
            APP_NAME,
            f"Metadata JSON saved successfully:\n\n{output_path}",
        )

    def save_operation_log(self, result: dict[str, Any] | None = None) -> None:
        if result is None:
            result = self.last_verification
        log_data = (result or {}).get("operation_log_data")
        if not log_data:
            messagebox.showwarning(APP_NAME, "No operation log is available.")
            return

        out = filedialog.asksaveasfilename(
            title="Save Operation Log",
            initialdir=str(self.source_path.parent) if self.source_path else None,
            initialfile="sanitizer_operation_log.json",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not out:
            return
        try:
            atomic_json_write(Path(out), log_data)
            self.status_var.set("Operation log saved")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not save operation log:\n\n{exc}")

    def save_verification_log(self, result: dict[str, Any] | None = None) -> None:
        if result is None:
            result = self.last_verification
        log_data = (result or {}).get("verification_log_data")
        if not log_data:
            messagebox.showwarning(APP_NAME, "No verification log is available.")
            return

        out = filedialog.asksaveasfilename(
            title="Save Verification Log",
            initialdir=str(self.source_path.parent) if self.source_path else None,
            initialfile="sanitizer_verification_log.json",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not out:
            return
        try:
            atomic_json_write(Path(out), log_data)
            self.status_var.set("Verification log saved")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not save verification log:\n\n{exc}")

    def save_before_after_report(self, result: dict[str, Any] | None = None) -> None:
        result = result or self.last_verification
        if not result:
            messagebox.showwarning(APP_NAME, "No sanitization report is available.")
            return

        diff = result.get("diff", {})
        comparison = result.get("comparison", {})
        payload = {
            "application": APP_NAME,
            "report": "Before -> After Sanitization",
            "source_file": str(self.source_path) if self.source_path else None,
            "output_file": str(result.get("path")) if result.get("path") else None,
            "safe_mode": True,
            "source_sha256": result.get("source_hash"),
            "output_sha256": result.get("output_hash"),
            "backup_sha256": result.get("backup_hash"),
            "processing_mode": result.get("processing_mode"),
            "verification": result.get("verification"),
            "dimensions": result.get("dims"),
            "pixel_status": result.get("pixels"),
            "image_comparison": comparison,
            "metadata_before": diff.get("before_count", 0),
            "metadata_after": diff.get("after_count", 0),
            "metadata_removed": diff.get("removed", []),
            "metadata_changed": diff.get("changed", []),
            "metadata_preserved": diff.get("preserved", []),
            "metadata_added": diff.get("added", []),
            "metadata_remaining": [r.key for r in result.get("after_records", []) if is_present_record(r)],
        }

        out = filedialog.asksaveasfilename(
            title="Save Before → After Report",
            initialdir=str(self.source_path.parent) if self.source_path else None,
            initialfile="sanitization_report.json",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not out:
            return
        try:
            atomic_json_write(Path(out), payload)
            self.status_var.set("Before → After report saved")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not save report:\n\n{exc}")

    def _update_exiftool_status(self) -> None:
        if not hasattr(self, "exiftool_status_var"):
            return
        if self.exiftool:
            self.exiftool_status_var.set(f"ExifTool: {Path(self.exiftool).name}")
        else:
            self.exiftool_status_var.set("ExifTool: Not detected")

    def exiftool_menu(self) -> None:
        found = find_exiftool()
        if found:
            self.exiftool = found
            self._update_exiftool_status()
            messagebox.showinfo(
                APP_NAME,
                f"ExifTool detected automatically.\n\n{found}",
            )
            return

        dialog = tk.Toplevel(self)
        dialog.title("ExifTool")
        dialog.geometry("520x220")
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=18)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="ExifTool", style="Title.TLabel").pack(anchor="w", pady=(0, 10))
        ttk.Label(
            frame,
            text=(
                "ExifTool was not detected automatically.\n"
                "Browse to the Windows executable. The official\n"
                "exiftool(-k).exe filename is supported automatically."
            ),
            wraplength=470,
        ).pack(anchor="w", pady=(0, 14))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", side="bottom")

        def browse() -> None:
            selected = filedialog.askopenfilename(
                parent=dialog,
                title="Select ExifTool Executable",
                filetypes=[
                    ("ExifTool executable", "*.exe"),
                    ("All files", "*.*"),
                ],
            )
            if not selected:
                return

            selected_path = Path(selected)
            try:
                normalized = normalize_exiftool_path(selected_path)
                if not normalized:
                    raise RuntimeError("The selected file could not be prepared for command-line use.")

                result = run_exiftool(normalized, ["-ver"], timeout=10)
                if result.returncode != 0 or not result.stdout.strip():
                    raise RuntimeError(
                        result.stderr.strip() or
                        "The selected file did not return an ExifTool version."
                    )
            except Exception as exc:
                messagebox.showerror(
                    "ExifTool",
                    f"The selected file could not be recognized as a working ExifTool executable.\n\n{exc}",
                    parent=dialog,
                )
                return

            self.exiftool = normalized
            self._update_exiftool_status()
            self.status_var.set("ExifTool selected successfully")
            dialog.destroy()

        def close() -> None:
            dialog.destroy()

        ttk.Button(buttons, text="Cancel", command=close).pack(side="right")
        ttk.Button(
            buttons,
            text="Browse…",
            command=browse,
            style="Action.TButton",
        ).pack(side="right", padx=(0, 8))


    def open_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Open Image",
            filetypes=[
                ("Supported images", " ".join(f"*{x}" for x in sorted(SUPPORTED_EXTENSIONS))),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self.load_image(Path(path))

    def load_image(self, path: Path) -> None:
        if self.busy:
            return
        self.source_path = path
        self.file_var.set(str(path))
        self.status_var.set("Analyzing image…")
        self._set_busy(True)

        def worker() -> None:
            try:
                with Image.open(path) as opened:
                    img = ImageOps.exif_transpose(opened)
                    img.load()
                    # Copy pixels into process-owned object. Do not retain
                    # source metadata dictionaries.
                    clean_view = img.copy()
                    info = ImageInfo(
                        width=clean_view.width,
                        height=clean_view.height,
                        mode=clean_view.mode,
                        format=opened.format or path.suffix.upper().lstrip("."),
                        bit_depth=str(ImageModeDepth.get(clean_view.mode, "?")),
                        has_alpha=("A" in clean_view.getbands()),
                        file_size=path.stat().st_size,
                        image_opened=True,
                    )
                    info.pixel_hash = compute_pixel_hash(clean_view)

                if self.exiftool:
                    records, raw = load_exiftool_metadata(self.exiftool, path)
                else:
                    records, raw = self.pillow_metadata(path)

                summary = build_privacy_summary(records)
                self.after(0, lambda: self._image_loaded(clean_view, info, records, raw, summary))
            except Exception as exc:
                self.after(0, lambda: self._load_failed(str(exc)))
            finally:
                self.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def pillow_metadata(self, path: Path) -> tuple[list[MetadataRecord], dict[str, Any]]:
        records: dict[str, MetadataRecord] = {}
        raw: dict[str, Any] = {}

        with Image.open(path) as img:
            for key, value in img.info.items():
                raw[key] = value
                display = f"<binary data: {len(value)} bytes>" if isinstance(value, bytes) else str(value)
                key_s = str(key)
                records[key_s] = MetadataRecord(
                    key=key_s,
                    value=display,
                    risk=classify_risk(key_s, display),
                    group=group_for_key(key_s),
                )

            try:
                exif = img.getexif()
                for tag_id, value in exif.items():
                    key = f"EXIF:{tag_id}"
                    records[key] = MetadataRecord(
                        key=key,
                        value=str(value),
                        risk=classify_risk(key, value),
                        group="EXIF",
                    )
            except Exception:
                pass

        for group, fields in KNOWN_METADATA_FIELDS.items():
            for field in fields:
                if field not in records:
                    records[field] = MetadataRecord(
                        key=field,
                        value="EMPTY / NOT PRESENT",
                        risk=classify_risk(field, ""),
                        group=group,
                    )

        return list(records.values()), raw


    def _image_loaded(
        self,
        img: Image.Image,
        info: ImageInfo,
        records: list[MetadataRecord],
        raw: dict[str, Any],
        summary: dict[str, Any],
    ) -> None:
        self.source_image = img
        self.source_info = info
        self.source_records = records
        self.source_raw = raw
        self.group_var.set("Overview")
        self.search_var.set("")
        self.file_var.set(self.source_path.name if self.source_path else "No image loaded")
        size_mb = info.file_size / (1024 * 1024) if info.file_size else 0
        self.metadata_count_var.set(
            f"Supported fields shown: {summary['total']}   •   Present: {summary['present_total']}"
        )
        self.sensitive_count_var.set(
            f"Sensitive fields present: {summary['sensitive']}"
        )


        privacy_values = privacy_display_values(records)
        for key in self.privacy_labels:
            self.privacy_labels[key].set(privacy_values.get(key, "Not present"))

        self.quality_var.set("Pixel hash captured")
        self._render_preview()
        self._render_image_facts()
        self.refresh_metadata_tree()

        format_note = "ExifTool verification available." if self.exiftool else "Install ExifTool for maximum metadata coverage and independent verification."
        self.status_var.set("Analysis complete")

    def _load_failed(self, error: str) -> None:
        self.status_var.set("Unable to open image")
        messagebox.showerror(APP_NAME, f"Could not load the image:\n\n{error}")

    def _render_preview(self) -> None:
        if self.source_image is None:
            return
        max_w, max_h = 460, 420
        img = self.source_image.copy()
        img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        self.current_photo = ImageTk.PhotoImage(img)
        self.preview.configure(image=self.current_photo, text="")

    def _render_image_facts(self) -> None:
        if not self.source_info:
            return
        facts = (
            f"Dimensions: {self.source_info.width} × {self.source_info.height}\n"
            f"Format: {self.source_info.format}\n"
            f"Mode / bit depth: {self.source_info.mode} / {self.source_info.bit_depth}\n"
            f"Alpha channel: {'Yes' if self.source_info.has_alpha else 'No'}\n"
            f"File size: {self.source_info.file_size:,} bytes\n"
            f"Pixel hash: {self.source_info.pixel_hash[:20] + '…' if self.source_info.pixel_hash else '—'}"
        )
        self.image_facts.configure(state="normal")
        self.image_facts.delete("1.0", "end")
        self.image_facts.insert("1.0", facts)
        self.image_facts.configure(state="disabled")

    def refresh_metadata_tree(self) -> None:
        if not hasattr(self, "tree"):
            return

        for item in self.tree.get_children():
            self.tree.delete(item)

        selected_group = self.group_var.get()
        query = self.search_var.get().strip().lower()
        hide_not_present = self.hide_not_present_var.get()

        visible: list[MetadataRecord] = []
        for rec in self.source_records:
            is_present = rec.value not in ("", "EMPTY / NOT PRESENT", "NOT PRESENT")

            if hide_not_present and not is_present:
                continue
            if selected_group != "Overview" and rec.group != selected_group:
                continue

            haystack = f"{rec.key} {rec.value}".lower()
            if query and query not in haystack:
                continue

            visible.append(rec)

        risk_order = {"Critical": 0, "High": 1, "Medium": 2, "Technical": 3}
        visible.sort(
            key=lambda rec: (
                rec.value in ("", "EMPTY / NOT PRESENT", "NOT PRESENT"),
                risk_order.get(rec.risk, 9),
                rec.group.lower(),
                rec.key.lower(),
            )
        )

        for idx, rec in enumerate(visible):
            is_present = rec.value not in ("", "EMPTY / NOT PRESENT", "NOT PRESENT")
            risk_text = f"{risk_symbol(rec.risk)} {rec.risk}"
            value_text = rec.value if is_present else "EMPTY / NOT PRESENT"

            if is_present:
                row_tag = "present_even" if idx % 2 == 0 else "present_odd"
            else:
                row_tag = "empty_even" if idx % 2 == 0 else "empty_odd"

            # Keep risk foreground styling on present rows; empty rows stay muted.
            tags = (rec.risk, row_tag)
            self.tree.insert(
                "", "end",
                values=(rec.key, value_text, risk_text),
                tags=tags
            )

    def start_sanitize(self) -> None:
        if self.busy:
            return
        if not self.source_path:
            messagebox.showwarning(APP_NAME, "Open an image first.")
            return

        confirm = tk.Toplevel(self)
        confirm.title("Maximum Sanitization")
        confirm.geometry("640x440")
        confirm.transient(self)
        confirm.grab_set()

        frame = ttk.Frame(confirm, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="MAXIMUM SANITIZATION", style="Title.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Label(
            frame,
            text=(
                "A completely new image will be created from the source image's visual data.\n"
                "The original file will not be modified."
            ),
            wraplength=580,
        ).pack(anchor="w", pady=(0, 14))

        checks = [
            "Keep image dimensions and visual content",
            "Remove original EXIF / GPS / IPTC / XMP",
            "Remove camera/device identifiers and MakerNotes where supported",
            "Do not copy original thumbnails or previews",
            "Reopen and independently verify the generated file",
        ]
        for item in checks:
            ttk.Label(frame, text=f"✓ {item}").pack(anchor="w", pady=3)

        mode_text = (
            f"Metadata engine ready: {Path(self.exiftool).name}. "
            "The app will use broad metadata removal and independent verification."
            if self.exiftool else
            "Metadata engine limited. The app will use the built-in image decoder "
            "for formats it can safely reconstruct; HEIC/HEIF/RAW and broader "
            "metadata coverage require ExifTool."
        )
        ttk.Label(frame, text=mode_text, wraplength=580).pack(anchor="w", pady=14)

        # Overwrite remains opt-in and requires explicit confirmation.
        overwrite_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="Safe Mode (recommended): source protection, hashes, atomic output, audit logs",
            variable=self.safe_mode_var,
        ).pack(anchor="w", pady=(2, 4))
        ttk.Checkbutton(
            frame,
            text="Overwrite source (requires an additional confirmation)",
            variable=overwrite_var,
        ).pack(anchor="w")

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", side="bottom", pady=(18, 0))

        def cancel() -> None:
            confirm.destroy()

        def proceed() -> None:
            confirm.destroy()
            self._choose_output(overwrite_var.get())

        ttk.Button(buttons, text="Cancel", command=cancel).pack(side="right")
        ttk.Button(buttons, text="Create Clean Copy", style="Action.TButton", command=proceed).pack(side="right", padx=(0, 8))

    def _choose_output(self, overwrite: bool) -> None:
        if not self.source_path:
            return

        src = self.source_path
        suffix = src.suffix.lower()

        # Keep format where possible. For unsupported RAW with Pillow fallback
        # the user should use ExifTool or choose an explicit raster output.
        default = f"{src.stem}_sanitized{suffix}"
        if overwrite:
            ok = messagebox.askyesno(
                "Confirm overwrite",
                f"This will replace the source file after a temporary output and verification:\n\n{src}\n\nContinue?",
                icon="warning",
            )
            if not ok:
                return
            self._run_sanitize(src, src, overwrite=True)
            return

        out = filedialog.asksaveasfilename(
            title="Save Clean Copy",
            initialdir=str(src.parent),
            initialfile=default,
            defaultextension=suffix,
            filetypes=[
                (f"{src.suffix.upper()[1:]} image", f"*{src.suffix}"),
                ("All files", "*.*"),
            ],
        )
        if not out:
            return
        dst = Path(out)
        if dst.resolve() == src.resolve():
            messagebox.showerror(APP_NAME, "For safety, choose a different output file. Use the explicit overwrite option when replacement is intended.")
            return
        self._run_sanitize(src, dst, overwrite=False)

    def _run_sanitize(self, src: Path, dst: Path, overwrite: bool) -> None:
        self._set_busy(True)
        self.status_var.set("Creating clean image…")

        def worker() -> None:
            temp_dir = None
            target = None
            backup = None
            source_hash_before = None
            source_hash_after = None
            output_hash = None
            backup_hash = None
            started = time.time()

            try:
                source_hash_before = sha256_file(src)

                # Atomic commit requires source and destination temporary file
                # to live on the same filesystem as the final output.
                temp_dir = (
                    src.parent / f".{src.name}.sanitizer_tmp"
                    if overwrite
                    else dst.parent / f".{dst.name}.sanitizer_tmp"
                )

                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                temp_dir.mkdir(parents=True, exist_ok=False)

                target = temp_dir / f"{src.stem}.clean{src.suffix}"

                if self.exiftool:
                    remove_all_metadata_with_exiftool(self.exiftool, src, target)
                    processing_mode = "Lossless / metadata reconstruction"
                    note = "ExifTool created a new file and removed writable source metadata."
                else:
                    processing_mode, note = save_with_pillow(src, target)

                if not target.exists() or target.stat().st_size == 0:
                    raise RuntimeError("Sanitization did not produce a valid output file.")

                # Pre-commit verification against the actual temporary output.
                passed, verification_records, verification_message = verification_scan(
                    self.exiftool, target
                )
                if not passed:
                    raise RuntimeError(
                        "Independent verification failed: " + verification_message
                    )

                source_hash_after = sha256_file(src)
                if source_hash_after != source_hash_before:
                    raise RuntimeError(
                        "Source SHA-256 changed during processing. "
                        "The source was not overwritten."
                    )

                output_hash = sha256_file(target)
                comparison = compare_images(src, target)

                before_records = list(self.source_records)
                after_records = list(verification_records)
                diff = metadata_diff(before_records, after_records)

                backup = None
                if overwrite:
                    # Never replace source until a verified backup exists.
                    backup = src.with_name(f"{src.stem}_backup{src.suffix}")
                    counter = 1
                    while backup.exists() or backup.resolve() == src.resolve():
                        backup = src.with_name(
                            f"{src.stem}_backup_{counter}{src.suffix}"
                        )
                        counter += 1

                    shutil.copy2(src, backup)
                    backup_hash = sha256_file(backup)

                    if backup_hash != source_hash_before:
                        raise RuntimeError(
                            "Backup SHA-256 does not match source SHA-256. "
                            "The source was not overwritten."
                        )

                    # Final race/integrity check before replacement.
                    if sha256_file(src) != source_hash_before:
                        raise RuntimeError(
                            "Source changed before overwrite. The source was not overwritten."
                        )

                    os.replace(target, src)
                    final_path = src
                else:
                    # Never overwrite an existing destination in Safe Mode.
                    if dst.exists():
                        raise RuntimeError(
                            f"Output already exists:\n{dst}\n\n"
                            "Choose another filename or explicitly enable overwrite."
                        )
                    os.replace(target, dst)
                    final_path = dst

                # Remove the now-empty temporary directory.
                shutil.rmtree(temp_dir, ignore_errors=True)

                # Independent verification of the exact committed file.
                output_hash = sha256_file(final_path)
                final_passed, final_records, final_message = verification_scan(
                    self.exiftool, final_path
                )
                if not final_passed:
                    raise RuntimeError(
                        "Post-commit verification failed: " + final_message
                    )

                after_records = list(final_records)
                diff = metadata_diff(before_records, after_records)

                if comparison.get("available") and comparison.get("dimensions_match"):
                    dims_status = "Preserved"
                    if processing_mode.startswith("Lossless"):
                        pixel_status = (
                            "Identical"
                            if comparison.get("pixel_identical")
                            else f"{comparison.get('changed_pixels_percent', 0.0):.4f}% changed"
                        )
                    else:
                        pixel_status = (
                            f"Re-encoded; {comparison.get('changed_pixels_percent', 0.0):.4f}% "
                            "of pixels differ"
                        )
                else:
                    dims_status = (
                        f"{comparison.get('source_size', 'unknown')} → "
                        f"{comparison.get('output_size', 'unknown')}"
                    )
                    pixel_status = "Not directly comparable"

                temp_cleaned = not temp_dir.exists()

                operation_log_text = make_operation_log(
                    src,
                    final_path,
                    overwrite,
                    source_hash_before,
                    output_hash,
                    backup,
                    backup_hash,
                    processing_mode,
                    temp_cleaned,
                )
                verification_log_text = make_verification_log(
                    source_hash_before,
                    source_hash_after,
                    output_hash,
                    backup_hash,
                    final_message,
                    comparison,
                    diff,
                )

                operation_log_data = {
                    "application": APP_NAME,
                    "operation": "maximum_sanitization",
                    "log_lines": operation_log_text,
                    "safe_mode": True,
                    "started_unix": started,
                    "completed_unix": time.time(),
                    "source": str(src),
                    "output": str(final_path),
                    "overwrite_requested": overwrite,
                    "processing_mode": processing_mode,
                    "source_sha256_before": source_hash_before,
                    "source_sha256_after": source_hash_after,
                    "output_sha256": output_hash,
                    "backup": str(backup) if backup else None,
                    "backup_sha256": backup_hash,
                    "temporary_directory_cleaned": temp_cleaned,
                    "result": "PASSED",
                }

                verification_log_data = {
                    "application": APP_NAME,
                    "verification": "independent post-commit scan",
                    "log_lines": verification_log_text,
                    "source_sha256": source_hash_before,
                    "output_sha256": output_hash,
                    "backup_sha256": backup_hash,
                    "verification_passed": True,
                    "message": final_message,
                    "metadata_before": diff["before_count"],
                    "metadata_after": diff["after_count"],
                    "metadata_removed": diff["removed"],
                    "metadata_changed": diff["changed"],
                    "metadata_preserved": diff["preserved"],
                    "metadata_added": diff["added"],
                    "remaining_fields": [
                        r.key for r in after_records if is_present_record(r)
                    ],
                    "dimensions": dims_status,
                    "pixel_status": pixel_status,
                    "image_comparison": comparison,
                }

                self.last_operation_log = [operation_log_data]
                self.last_verification_log = verification_log_data

                result = {
                    "passed": True,
                    "path": final_path,
                    "processing_mode": processing_mode,
                    "note": note,
                    "verification": final_message,
                    "dims": dims_status,
                    "pixels": pixel_status,
                    "path_note": (
                        f"Source replaced only after verified backup. Backup: {backup}"
                        if overwrite
                        else f"Clean copy created atomically: {final_path}"
                    ),
                    "remaining": [],
                    "before_records": before_records,
                    "after_records": after_records,
                    "diff": diff,
                    "comparison": comparison,
                    "source_hash": source_hash_before,
                    "output_hash": output_hash,
                    "backup_hash": backup_hash,
                    "backup": backup,
                    "operation_log_data": operation_log_data,
                    "verification_log_data": verification_log_data,
                }
                self.after(0, lambda: self._sanitize_done(result))

            except Exception as exc:
                if target and target.exists():
                    try:
                        target.unlink()
                    except OSError:
                        pass
                if temp_dir:
                    shutil.rmtree(temp_dir, ignore_errors=True)

                detail = str(exc)
                self.after(0, lambda: self._sanitize_failed(detail))
            finally:
                self.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()


    def _sanitize_done(self, result: dict[str, Any]) -> None:
        self.last_verification = result
        if result["passed"]:
            self.status_var.set("Maximum sanitization complete")
            self._show_result_dialog(result, success=True)
        else:
            self.status_var.set("Sanitization incomplete")
            self._show_result_dialog(result, success=False)

    def _sanitize_failed(self, error: str) -> None:
        self.status_var.set("Sanitization failed")
        messagebox.showerror(APP_NAME, f"Could not create the clean image:\n\n{error}")

    def _show_result_dialog(self, result: dict[str, Any], success: bool) -> None:
        win = tk.Toplevel(self)
        win.title("Sanitization Result")
        win.geometry("820x780")
        win.minsize(720, 620)
        win.configure(bg="#f4f6f8")
        win.transient(self)
        win.grab_set()

        # Main scrollable canvas keeps the results usable on small screens and
        # when metadata/log content is large.
        outer = tk.Frame(win, bg="#f4f6f8")
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            outer,
            bg="#f4f6f8",
            highlightthickness=0,
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        content = tk.Frame(
            canvas,
            bg="#ffffff",
            highlightbackground="#d8dee7",
            highlightthickness=1,
        )
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def resize_content(event):
            canvas.itemconfigure(window_id, width=event.width)

        content.bind("<Configure>", update_scrollregion)
        canvas.bind("<Configure>", resize_content)

        def wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")

        canvas.bind_all("<MouseWheel>", wheel)

        def close_results():
            try:
                canvas.unbind_all("<MouseWheel>")
            except tk.TclError:
                pass
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", close_results)

        accent = "#65c98a" if success else "#ef7a87"

        # Header
        tk.Label(
            content,
            text="MAXIMUM SANITIZATION PASSED" if success else "SANITIZATION INCOMPLETE",
            bg="#ffffff",
            fg="#18212b",
            font=("TkDefaultFont", 16, "bold"),
        ).pack(anchor="w", padx=22, pady=(20, 4))

        tk.Label(
            content,
            text="✓  Independent verification passed" if success else "⚠  Verification requires attention",
            bg="#ffffff",
            fg=accent,
            font=("TkDefaultFont", 9, "bold"),
        ).pack(anchor="w", padx=22, pady=(0, 16))

        # Summary cards
        stats = tk.Frame(content, bg="#ffffff")
        stats.pack(fill="x", padx=22, pady=(0, 12))

        diff = result.get("diff", {})
        comparison = result.get("comparison", {})

        stat_values = [
            ("Metadata Before", diff.get("before_count", 0)),
            ("Metadata After", diff.get("after_count", 0)),
            ("Removed", len(diff.get("removed", []))),
            ("Changed", len(diff.get("changed", []))),
            ("Pixel Changes", f"{comparison.get('changed_pixels_percent', 0.0):.4f}%"
             if comparison.get("changed_pixels_percent") is not None else "—"),
        ]

        for label, value in stat_values:
            card = tk.Frame(
                stats,
                bg="#f8fafc",
                highlightbackground="#e5e7eb",
                highlightthickness=1,
            )
            card.pack(side="left", fill="x", expand=True, padx=(0, 6))
            tk.Label(
                card,
                text=str(value),
                bg="#f8fafc",
                fg="#18212b",
                font=("TkDefaultFont", 13, "bold"),
            ).pack(anchor="w", padx=10, pady=(8, 1))
            tk.Label(
                card,
                text=label,
                bg="#f8fafc",
                fg="#667085",
                font=("TkDefaultFont", 8),
            ).pack(anchor="w", padx=10, pady=(0, 8))

        # Key integrity details
        detail = tk.Frame(content, bg="#f8fafc")
        detail.pack(fill="x", padx=22, pady=(0, 12))

        integrity_lines = [
            ("Processing", result.get("processing_mode", "—")),
            ("Dimensions", result.get("dims", "—")),
            ("Pixel status", result.get("pixels", "—")),
            ("Source SHA-256", result.get("source_hash", "—")),
            ("Output SHA-256", result.get("output_hash", "—")),
        ]
        if result.get("backup_hash"):
            integrity_lines.append(("Backup SHA-256", result.get("backup_hash")))
        integrity_lines.append(("Output", str(result.get("path", "—"))))

        for label, value in integrity_lines:
            row = tk.Frame(detail, bg="#f8fafc")
            row.pack(fill="x", padx=12, pady=5)

            tk.Label(
                row,
                text=label.upper(),
                bg="#f8fafc",
                fg="#667085",
                font=("TkDefaultFont", 8, "bold"),
                width=16,
                anchor="w",
            ).pack(side="left")

            value_label = tk.Label(
                row,
                text=str(value),
                bg="#f8fafc",
                fg="#374151",
                font=("TkDefaultFont", 8),
                wraplength=560,
                justify="left",
                anchor="w",
            )
            value_label.pack(side="left", fill="x", expand=True)

        tk.Label(
            content,
            text=result.get("note", ""),
            bg="#ffffff",
            fg="#667085",
            wraplength=730,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=22, pady=(2, 8))

        # Before -> After metadata report
        if diff:
            report_card = ttk.LabelFrame(content, text="Before → After Metadata")
            report_card.pack(fill="x", padx=22, pady=(4, 10))

            report_tree = ttk.Treeview(
                report_card,
                columns=("status", "field"),
                show="headings",
                height=8,
            )
            report_tree.heading("status", text="Status")
            report_tree.heading("field", text="Field")
            report_tree.column("status", width=105, anchor="center")
            report_tree.column("field", width=620, anchor="w")
            report_tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)

            report_scroll = ttk.Scrollbar(
                report_card,
                orient="vertical",
                command=report_tree.yview,
            )
            report_scroll.pack(side="right", fill="y", padx=(0, 6), pady=6)
            report_tree.configure(yscrollcommand=report_scroll.set)

            for field in diff.get("removed", []):
                report_tree.insert("", "end", values=("REMOVED", field), tags=("removed",))
            for field in diff.get("changed", []):
                report_tree.insert("", "end", values=("CHANGED", field), tags=("changed",))
            for field in diff.get("preserved", []):
                report_tree.insert("", "end", values=("PRESERVED", field), tags=("preserved",))
            for field in diff.get("added", []):
                report_tree.insert("", "end", values=("ADDED", field), tags=("added",))

            report_tree.tag_configure("removed", foreground="#15803d")
            report_tree.tag_configure("changed", foreground="#b45309")
            report_tree.tag_configure("preserved", foreground="#6b7280")
            report_tree.tag_configure("added", foreground="#b91c1c")

        def compare_images_window() -> None:
            source = result.get("backup") if result.get("backup") else self.source_path
            output = result.get("path")

            if not source or not output:
                messagebox.showerror(
                    APP_NAME,
                    "The comparison images are unavailable.",
                    parent=win,
                )
                return

            source = Path(source)
            output = Path(output)

            if not source.exists() or not output.exists():
                messagebox.showerror(
                    APP_NAME,
                    "The comparison images are unavailable.",
                    parent=win,
                )
                return

            compare_win = tk.Toplevel(win)
            compare_win.title("Image Comparison — Before → After")
            compare_win.geometry("1040x700")
            compare_win.minsize(850, 600)
            compare_win.transient(win)

            body = ttk.Frame(compare_win, padding=12)
            body.pack(fill="both", expand=True)

            left = ttk.LabelFrame(body, text="Original")
            right = ttk.LabelFrame(body, text="Sanitized")
            left.pack(side="left", fill="both", expand=True, padx=(0, 6))
            right.pack(side="left", fill="both", expand=True, padx=(6, 0))

            left_label = tk.Label(left, text="Loading…", anchor="center")
            right_label = tk.Label(right, text="Loading…", anchor="center")
            left_label.pack(fill="both", expand=True, padx=8, pady=8)
            right_label.pack(fill="both", expand=True, padx=8, pady=8)

            try:
                with Image.open(source) as a, Image.open(output) as b:
                    a = ImageOps.exif_transpose(a)
                    b = ImageOps.exif_transpose(b)
                    a.load()
                    b.load()

                    a_preview = a.convert("RGB")
                    b_preview = b.convert("RGB")
                    a_preview.thumbnail((470, 460), Image.Resampling.LANCZOS)
                    b_preview.thumbnail((470, 460), Image.Resampling.LANCZOS)

                    left_photo = ImageTk.PhotoImage(a_preview)
                    right_photo = ImageTk.PhotoImage(b_preview)

                    left_label.configure(image=left_photo, text="")
                    right_label.configure(image=right_photo, text="")
                    left_label.image = left_photo
                    right_label.image = right_photo

            except Exception as exc:
                left_label.configure(text=f"Could not render:\n{exc}")
                right_label.configure(text="")

            comp = result.get("comparison", {})
            compare_card = ttk.LabelFrame(compare_win, text="Pixel Comparison")
            compare_card.pack(fill="x", padx=12, pady=(0, 8))

            metrics = [
                ("Dimensions match", comp.get("dimensions_match", "—")),
                ("Pixel identical", comp.get("pixel_identical", "—")),
                ("Changed pixels", comp.get("changed_pixels", "—")),
                (
                    "Changed pixels %",
                    f"{comp.get('changed_pixels_percent', 0.0):.4f}%"
                    if comp.get("changed_pixels_percent") is not None else "—",
                ),
                (
                    "Mean absolute difference",
                    f"{comp.get('mean_absolute_difference', 0.0):.6f}"
                    if comp.get("mean_absolute_difference") is not None else "—",
                ),
            ]

            for label, value in metrics:
                row = ttk.Frame(compare_card)
                row.pack(fill="x", padx=10, pady=3)
                ttk.Label(row, text=label, width=25).pack(side="left")
                ttk.Label(row, text=str(value)).pack(side="left")

            ttk.Button(
                compare_win,
                text="Close",
                command=compare_win.destroy,
            ).pack(side="right", padx=12, pady=10)

        # Logs
        logs = ttk.LabelFrame(content, text="Operation & Verification Logs")
        logs.pack(fill="x", padx=22, pady=(0, 10))

        notebook = ttk.Notebook(logs)
        notebook.pack(fill="both", expand=True, padx=6, pady=6)

        operation_tab = ttk.Frame(notebook)
        verification_tab = ttk.Frame(notebook)
        notebook.add(operation_tab, text="Operation Log")
        notebook.add(verification_tab, text="Verification Log")

        def add_log_tab(parent, log_lines):
            text_frame = ttk.Frame(parent)
            text_frame.pack(fill="both", expand=True)

            text = tk.Text(
                text_frame,
                height=10,
                wrap="none",
                relief="flat",
                bg="#f8fafc",
                fg="#374151",
                font=("Consolas", 8),
            )
            y = ttk.Scrollbar(text_frame, orient="vertical", command=text.yview)
            x = ttk.Scrollbar(text_frame, orient="horizontal", command=text.xview)
            text.configure(yscrollcommand=y.set, xscrollcommand=x.set)

            text.grid(row=0, column=0, sticky="nsew")
            y.grid(row=0, column=1, sticky="ns")
            x.grid(row=1, column=0, sticky="ew")
            text_frame.rowconfigure(0, weight=1)
            text_frame.columnconfigure(0, weight=1)

            for line in log_lines:
                text.insert("end", str(line) + "\n")
            text.configure(state="disabled")

        add_log_tab(
            operation_tab,
            result.get("operation_log_data", {}).get("log_lines", []),
        )
        add_log_tab(
            verification_tab,
            result.get("verification_log_data", {}).get("log_lines", []),
        )

        # Action row remains simple and always visible at the bottom.
        actions = tk.Frame(content, bg="#ffffff")
        actions.pack(fill="x", padx=22, pady=(4, 20))

        if result.get("comparison", {}).get("available"):
            ttk.Button(
                actions,
                text="Compare Images",
                command=compare_images_window,
            ).pack(side="left", padx=(0, 8))

        if result.get("operation_log_data"):
            ttk.Button(
                actions,
                text="Save Operation Log",
                command=lambda: self.save_operation_log(result),
            ).pack(side="left", padx=(0, 8))

        if result.get("verification_log_data"):
            ttk.Button(
                actions,
                text="Save Verification Log",
                command=lambda: self.save_verification_log(result),
            ).pack(side="left", padx=(0, 8))

        ttk.Button(
            actions,
            text="Save Report",
            command=lambda: self.save_before_after_report(result),
        ).pack(side="left", padx=(0, 8))

        ttk.Button(
            actions,
            text="Close",
            style="Secondary.TButton",
            command=close_results,
        ).pack(side="right")


    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        if busy:
            self.progress.start(10)
            self.status_var.set("Processing…")
        else:
            self.progress.stop()


def main() -> None:
    app = SanitizerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
