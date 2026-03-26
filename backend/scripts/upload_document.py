#!/usr/bin/env python3
"""Upload a document or archive to Lexiro via REST API and wait for processing."""

import argparse
import os
import sys
import time

import requests


def _upload_single(args):
    """Upload a single document file."""
    file_size = os.path.getsize(args.file)
    filename = os.path.basename(args.file)
    print(f"File:    {args.file}")
    print(f"Size:    {file_size:,} bytes ({file_size / 1024 / 1024:.1f} MB)")
    print(f"Product: {args.product}")
    print(f"Version: {args.version}")
    print(f"API:     {args.api_url}")
    print()

    ingest_url = f"{args.api_url}/api/v1/documents/ingest"
    print(f"Uploading to {ingest_url} ...")

    t0 = time.time()
    with open(args.file, "rb") as f:
        resp = requests.post(
            ingest_url,
            files={"file": (filename, f, "application/octet-stream")},
            data={
                "product_name": args.product,
                "firmware_version": args.version,
                "manufacturer": args.manufacturer,
                "format": args.format,
                "force": "true" if args.force else "false",
            },
            timeout=120,
        )

    if resp.status_code not in (200, 202):
        print(f"ERROR: Upload failed — HTTP {resp.status_code}", file=sys.stderr)
        print(resp.text, file=sys.stderr)
        sys.exit(1)

    result = resp.json()

    if result.get("status") == "skipped":
        print(f"\nSKIPPED: {result['message']}")
        sys.exit(0)

    doc_id = result["document_id"]
    task_id = result.get("task_id", "—")
    upload_sec = round(time.time() - t0, 1)

    print(f"Uploaded in {upload_sec}s — document_id={doc_id}, task_id={task_id}")

    if args.no_wait:
        print(f"\nCheck status: GET {args.api_url}/api/v1/documents/{doc_id}")
        sys.exit(0)

    _wait_for_document(args.api_url, doc_id, args.timeout, t0)


_ARCHIVE_CONTENT_TYPES = {
    ".zip": "application/zip",
    ".7z": "application/x-7z-compressed",
    ".tar": "application/x-tar",
    ".tar.gz": "application/gzip",
    ".tgz": "application/gzip",
    ".tar.bz2": "application/x-bzip2",
    ".tar.xz": "application/x-xz",
    ".rar": "application/vnd.rar",
}


def _archive_ext(filename: str) -> str:
    lower = filename.lower()
    for compound in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if lower.endswith(compound):
            return compound
    return os.path.splitext(lower)[1]


def _upload_archive(args):
    """Upload an archive (ZIP, 7z, tar, RAR)."""
    file_size = os.path.getsize(args.file)
    filename = os.path.basename(args.file)
    print(f"Archive: {args.file}")
    print(f"Size:    {file_size:,} bytes ({file_size / 1024 / 1024:.1f} MB)")
    print(f"Product: {args.product}")
    print(f"Version: {args.version}")
    print(f"API:     {args.api_url}")
    print()

    ingest_url = f"{args.api_url}/api/v1/documents/ingest-archive"
    print(f"Uploading archive to {ingest_url} ...")

    ext = _archive_ext(filename)
    content_type = _ARCHIVE_CONTENT_TYPES.get(ext, "application/octet-stream")

    t0 = time.time()
    with open(args.file, "rb") as f:
        resp = requests.post(
            ingest_url,
            files={"file": (filename, f, content_type)},
            data={
                "product_name": args.product,
                "firmware_version": args.version,
                "manufacturer": args.manufacturer,
                "force": "true" if args.force else "false",
            },
            timeout=300,
        )

    if resp.status_code not in (200, 202):
        print(f"ERROR: Upload failed — HTTP {resp.status_code}", file=sys.stderr)
        print(resp.text, file=sys.stderr)
        sys.exit(1)

    result = resp.json()
    upload_sec = round(time.time() - t0, 1)

    print(f"\nArchive uploaded in {upload_sec}s")
    print(f"  Product:  {result['product_name']}")
    print(f"  Files:    {result['total_files']}")
    print(f"  Accepted: {result['accepted']}")
    print(f"  Skipped:  {result['skipped']}")
    print(f"  Errors:   {result['errors']}")
    print()

    for f_result in result.get("files", []):
        status_icon = {"pending": "[...]", "skipped": "[skip]", "error": "[ERR]"}.get(f_result["status"], "?")
        doc_id = f_result.get("document_id", "—")
        print(f"  {status_icon} {f_result['filename']} -> {f_result['status']} (doc_id={doc_id})")
        if f_result.get("message"):
            print(f"     {f_result['message']}")

    if args.no_wait:
        sys.exit(0)

    pending_docs = [
        f_result["document_id"]
        for f_result in result.get("files", [])
        if f_result["status"] == "pending" and f_result.get("document_id")
    ]

    if pending_docs:
        print(f"\nWaiting for {len(pending_docs)} documents to process...")
        for doc_id in pending_docs:
            _wait_for_document(args.api_url, doc_id, args.timeout, t0)


def _wait_for_document(api_url: str, doc_id: int, timeout: int, t0: float):
    """Poll document status until ready/error/timeout."""
    print(f"\nWaiting for document {doc_id}", end="", flush=True)
    status_url = f"{api_url}/api/v1/documents/{doc_id}"
    deadline = time.time() + timeout

    while time.time() < deadline:
        time.sleep(5)
        try:
            info = requests.get(status_url, timeout=10).json()
        except Exception as e:
            print(f"\n  WARNING: Status check failed: {e}", flush=True)
            continue

        status = info["status"]
        chunks = info["total_chunks"]

        if status == "ready":
            total_sec = round(time.time() - t0, 1)
            print(f"\n  SUCCESS in {total_sec}s")
            print(f"    Document ID: {doc_id}")
            print(f"    Title:       {info['title']}")
            print(f"    Format:      {info['format']}")
            print(f"    Chunks:      {chunks}")
            return

        if status == "error":
            print(f"\n  ERROR: Ingestion failed for doc {doc_id}", file=sys.stderr)
            print(f"    Error: {info.get('error_message', '?')}", file=sys.stderr)
            return

        print(".", end="", flush=True)

    print(f"\n  TIMEOUT: doc {doc_id} still processing after {timeout}s", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Upload a document or ZIP archive to Lexiro and track ingestion progress.",
    )
    parser.add_argument("file", help="Path to document file or archive (ZIP, 7z, tar.gz, tgz, tar.bz2, tar.xz, tar, RAR)")
    parser.add_argument("--product", required=True, help="Product name (e.g. 'HikCentral Professional')")
    parser.add_argument("--version", default="1.0", help="Firmware/API version (default: 1.0)")
    parser.add_argument("--manufacturer", default="", help="Manufacturer name")
    parser.add_argument("--format", default="auto", choices=["auto", "markdown", "swagger", "pdf", "proto"],
                        help="Document format (default: auto-detect)")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--force", action="store_true", help="Force re-upload even if document already exists (bypass deduplication)")
    parser.add_argument("--no-wait", action="store_true", help="Don't wait for processing, return immediately")
    parser.add_argument("--timeout", type=int, default=600, help="Max wait time in seconds (default: 600)")

    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"ERROR: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    ext = _archive_ext(args.file)
    if ext in _ARCHIVE_CONTENT_TYPES:
        _upload_archive(args)
    else:
        _upload_single(args)


if __name__ == "__main__":
    main()
