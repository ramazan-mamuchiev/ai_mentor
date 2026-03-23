#!/usr/bin/env python3
"""Offline document-to-Markdown converter.

Converts files (and archives) to Markdown using the same converters as the
IPCodex ingestion pipeline, but without touching the database or any other
system component.  Output ``.md`` files are written next to the originals
(or into --output-dir) with the same base name.

Supported single-file formats:
    .pdf, .proto, .yaml/.yml/.json (Swagger/OpenAPI), .md, .txt, .wsdl, .xml

Supported archive formats:
    .zip, .7z, .tar, .tar.gz, .tgz, .tar.bz2, .tar.xz, .rar

Usage examples:
    python convert_to_md.py document.pdf
    python convert_to_md.py spec.yaml proto.proto readme.md
    python convert_to_md.py archive.zip --output-dir ./converted
    python convert_to_md.py docs/ --recursive
    python convert_to_md.py document.pdf --ocr-mode always --ocr-languages en,ru
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.ingestion.converters.pdf import convert_pdf
from app.ingestion.converters.proto import convert_proto_file
from app.ingestion.converters.swagger import convert_swagger_file, is_swagger_file
from app.documents.archive import (
    ARCHIVE_ALLOWED_EXTENSIONS,
    SUPPORTED_ARCHIVE_EXTENSIONS,
    extract_archive,
    _archive_ext,
)

SINGLE_FILE_EXTENSIONS = ARCHIVE_ALLOWED_EXTENSIONS

_COUNTS = {"ok": 0, "error": 0, "skip": 0}


def detect_format(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".md":
        return "markdown"
    if ext == ".pdf":
        return "pdf"
    if ext == ".proto":
        return "proto"
    if ext in (".yaml", ".yml", ".json"):
        if is_swagger_file(file_path):
            return "swagger"
        if ext == ".json":
            return "markdown"
        return "swagger"
    return "markdown"


def convert_single_file(
    file_path: str,
    output_path: str,
    *,
    ocr_mode: str = "auto",
    ocr_languages: str = "en,ru",
) -> bool:
    """Convert one file to Markdown and write the result to *output_path*.

    Returns True on success.
    """
    fmt = detect_format(file_path)

    try:
        if fmt == "pdf":
            text, meta = convert_pdf(file_path, ocr_mode=ocr_mode, ocr_languages=ocr_languages)
            extra = f"pages={meta.get('pages')}, ocr={meta.get('ocr_applied')}"
        elif fmt == "swagger":
            text, meta = convert_swagger_file(file_path)
            extra = f"endpoints={meta.get('endpoints')}, models={meta.get('models')}"
        elif fmt == "proto":
            text, meta = convert_proto_file(file_path)
            extra = f"services={meta.get('services')}, messages={meta.get('messages')}"
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                text = f.read()
            extra = "copy"
    except Exception as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        return False

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)

    size_kb = round(os.path.getsize(output_path) / 1024, 1)
    print(f"  -> {output_path}  ({size_kb} KB, fmt={fmt}, {extra})")
    return True


def _output_md_path(source_path: str, output_dir: str | None) -> str:
    base = os.path.splitext(source_path)[0] + ".md"
    if output_dir:
        rel = os.path.basename(base)
        return os.path.join(output_dir, rel)
    return base


def process_archive(
    archive_path: str,
    output_dir: str | None,
    *,
    ocr_mode: str = "auto",
    ocr_languages: str = "en,ru",
):
    """Extract an archive and convert every inner file."""
    print(f"\nArchive: {archive_path}")
    with open(archive_path, "rb") as f:
        data = f.read()

    try:
        entries = extract_archive(data, os.path.basename(archive_path))
    except Exception as exc:
        print(f"  ERROR extracting archive: {exc}", file=sys.stderr)
        _COUNTS["error"] += 1
        return

    if not entries:
        print("  (no supported files inside archive)")
        _COUNTS["skip"] += 1
        return

    archive_base = os.path.splitext(os.path.basename(archive_path))[0]
    ext = _archive_ext(archive_path)
    if ext in (".tar.gz", ".tar.bz2", ".tar.xz"):
        archive_base = os.path.splitext(archive_base)[0]

    dest_root = output_dir or os.path.join(os.path.dirname(archive_path), archive_base + "_md")

    print(f"  {len(entries)} file(s) found, output -> {dest_root}")

    for arc_name, file_bytes in entries:
        inner_base = os.path.splitext(arc_name)[0] + ".md"
        out_path = os.path.join(dest_root, inner_base)

        with tempfile.NamedTemporaryFile(
            suffix=os.path.splitext(arc_name)[1],
            delete=False,
        ) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        try:
            print(f"  [{arc_name}]")
            ok = convert_single_file(
                tmp_path, out_path, ocr_mode=ocr_mode, ocr_languages=ocr_languages,
            )
            _COUNTS["ok" if ok else "error"] += 1
        finally:
            os.unlink(tmp_path)


def process_path(
    path: str,
    output_dir: str | None,
    *,
    recursive: bool = False,
    ocr_mode: str = "auto",
    ocr_languages: str = "en,ru",
):
    if os.path.isdir(path):
        if not recursive:
            print(f"SKIP directory (use --recursive): {path}", file=sys.stderr)
            _COUNTS["skip"] += 1
            return
        for root, _dirs, files in os.walk(path):
            for fname in sorted(files):
                full = os.path.join(root, fname)
                process_path(
                    full, output_dir,
                    recursive=False, ocr_mode=ocr_mode, ocr_languages=ocr_languages,
                )
        return

    ext = _archive_ext(path)
    if ext in SUPPORTED_ARCHIVE_EXTENSIONS:
        process_archive(path, output_dir, ocr_mode=ocr_mode, ocr_languages=ocr_languages)
        return

    file_ext = os.path.splitext(path)[1].lower()
    if file_ext not in SINGLE_FILE_EXTENSIONS:
        print(f"SKIP unsupported extension '{file_ext}': {path}", file=sys.stderr)
        _COUNTS["skip"] += 1
        return

    out = _output_md_path(path, output_dir)
    if out == path:
        print(f"SKIP (already .md): {path}")
        _COUNTS["skip"] += 1
        return

    print(f"\nFile: {path}")
    ok = convert_single_file(path, out, ocr_mode=ocr_mode, ocr_languages=ocr_languages)
    _COUNTS["ok" if ok else "error"] += 1


def main():
    parser = argparse.ArgumentParser(
        description="Convert documents to Markdown offline (no DB, no API).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "paths", nargs="+",
        help="Files, archives, or directories to convert",
    )
    parser.add_argument(
        "--output-dir", "-o", default=None,
        help="Write all .md files into this directory (default: next to originals)",
    )
    parser.add_argument(
        "--recursive", "-r", action="store_true",
        help="Recurse into directories",
    )
    parser.add_argument(
        "--ocr-mode", default="auto", choices=["auto", "always", "off"],
        help="OCR mode for PDF files (default: auto)",
    )
    parser.add_argument(
        "--ocr-languages", default="en,ru",
        help="Comma-separated OCR language codes, e.g. 'en,ru,ch_sim' (default: en,ru)",
    )
    args = parser.parse_args()

    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)

    t0 = time.time()

    for p in args.paths:
        p = os.path.normpath(p)
        if not os.path.exists(p):
            print(f"ERROR: not found: {p}", file=sys.stderr)
            _COUNTS["error"] += 1
            continue
        process_path(
            p, args.output_dir,
            recursive=args.recursive,
            ocr_mode=args.ocr_mode,
            ocr_languages=args.ocr_languages,
        )

    elapsed = round(time.time() - t0, 1)
    total = _COUNTS["ok"] + _COUNTS["error"] + _COUNTS["skip"]
    print(f"\nDone in {elapsed}s — {total} item(s): "
          f"{_COUNTS['ok']} converted, {_COUNTS['error']} errors, {_COUNTS['skip']} skipped")

    sys.exit(1 if _COUNTS["error"] else 0)


if __name__ == "__main__":
    main()
