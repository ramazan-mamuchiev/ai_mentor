#!/usr/bin/env python3
"""Upload a document to IPCodex via REST API and wait for processing."""

import argparse
import os
import sys
import time

import requests


def main():
    parser = argparse.ArgumentParser(
        description="Upload a document to IPCodex and track ingestion progress.",
    )
    parser.add_argument("file", help="Path to the document file (PDF, MD, YAML, JSON)")
    parser.add_argument("--device", required=True, help="Device name (e.g. 'HikCentral Professional')")
    parser.add_argument("--version", default="1.0", help="Firmware/API version (default: 1.0)")
    parser.add_argument("--manufacturer", default="", help="Manufacturer name")
    parser.add_argument("--format", default="auto", choices=["auto", "markdown", "swagger", "pdf"],
                        help="Document format (default: auto-detect)")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--no-wait", action="store_true", help="Don't wait for processing, return immediately")
    parser.add_argument("--timeout", type=int, default=600, help="Max wait time in seconds (default: 600)")

    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"ERROR: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    file_size = os.path.getsize(args.file)
    filename = os.path.basename(args.file)
    print(f"File:    {args.file}")
    print(f"Size:    {file_size:,} bytes ({file_size / 1024 / 1024:.1f} MB)")
    print(f"Device:  {args.device}")
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
                "device_name": args.device,
                "firmware_version": args.version,
                "manufacturer": args.manufacturer,
                "format": args.format,
            },
            timeout=120,
        )

    if resp.status_code != 202:
        print(f"ERROR: Upload failed — HTTP {resp.status_code}", file=sys.stderr)
        print(resp.text, file=sys.stderr)
        sys.exit(1)

    result = resp.json()
    doc_id = result["document_id"]
    task_id = result.get("task_id", "—")
    upload_sec = round(time.time() - t0, 1)

    print(f"Uploaded in {upload_sec}s — document_id={doc_id}, task_id={task_id}")

    if args.no_wait:
        print(f"\nCheck status: GET {args.api_url}/api/v1/documents/{doc_id}")
        sys.exit(0)

    print("\nWaiting for processing", end="", flush=True)
    status_url = f"{args.api_url}/api/v1/documents/{doc_id}"
    deadline = time.time() + args.timeout

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
            print(f"\n\nSUCCESS in {total_sec}s")
            print(f"  Document ID: {doc_id}")
            print(f"  Title:       {info['title']}")
            print(f"  Format:      {info['format']}")
            print(f"  Chunks:      {chunks}")
            print(f"  File:        {info['original_filename']}")
            sys.exit(0)

        if status == "error":
            print(f"\n\nERROR: Ingestion failed", file=sys.stderr)
            print(f"  Document ID: {doc_id}", file=sys.stderr)
            print(f"  Error:       {info.get('error_message', '?')}", file=sys.stderr)
            sys.exit(1)

        print(".", end="", flush=True)

    print(f"\n\nTIMEOUT: Still processing after {args.timeout}s", file=sys.stderr)
    print(f"Check manually: GET {status_url}", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
