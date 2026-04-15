#!/usr/bin/env python3
"""Check document ingestion status in Lexiro.

Examples:
    # All documents summary
    python check_documents.py

    # Filter by product
    python check_documents.py --product "Axxon One"

    # Show only errors
    python check_documents.py --status error

    # Show only pending/processing (queue)
    python check_documents.py --status pending,processing

    # Single document details
    python check_documents.py --id 42

    # Watch mode: poll every 10s until queue is empty
    python check_documents.py --product "Axxon One" --watch

    # Custom API URL
    python check_documents.py --api-url http://192.168.1.10:8000
"""

import argparse
import sys
import time
from datetime import datetime, timezone

import requests


def _fetch_documents(api_url: str, timeout: int = 30) -> list[dict]:
    r = requests.get(f"{api_url}/api/v1/documents/", params={"limit": "1000"}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _fetch_single(api_url: str, doc_id: int, timeout: int = 10) -> dict:
    r = requests.get(f"{api_url}/api/v1/documents/{doc_id}", timeout=timeout)
    r.raise_for_status()
    return r.json()


def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}" if unit != "B" else f"{nbytes} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


def _age(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s ago"
        if secs < 3600:
            return f"{secs // 60}m ago"
        if secs < 86400:
            return f"{secs // 3600}h {(secs % 3600) // 60}m ago"
        return f"{secs // 86400}d ago"
    except Exception:
        return iso_str


def _status_icon(status: str) -> str:
    return {
        "ready": "[OK]",
        "pending": "[..]",
        "processing": "[>>]",
        "error": "[!!]",
    }.get(status, "[??]")


def _print_summary(docs: list[dict]):
    statuses: dict[str, int] = {}
    total_size = 0
    total_chunks = 0
    products: dict[str, int] = {}

    for d in docs:
        st = d["status"]
        statuses[st] = statuses.get(st, 0) + 1
        total_size += d.get("file_size_bytes", 0)
        total_chunks += d.get("total_chunks", 0)
        pn = d.get("product_name", "?")
        products[pn] = products.get(pn, 0) + 1

    print(f"Documents: {len(docs)}  |  Chunks: {total_chunks}  |  Size: {_human_size(total_size)}")
    parts = []
    for st in ("ready", "processing", "pending", "error"):
        if st in statuses:
            parts.append(f"{st}={statuses[st]}")
    print(f"Status:    {', '.join(parts)}")
    if len(products) > 1:
        print(f"Products:  {', '.join(f'{k} ({v})' for k, v in sorted(products.items()))}")
    elif products:
        print(f"Product:   {list(products.keys())[0]}")
    print()


def _print_table(docs: list[dict]):
    if not docs:
        print("  (no documents)")
        return

    hdr = f"  {'ID':>5}  {'Status':<11}  {'Chunks':>6}  {'Size':>10}  {'Format':<10}  {'Age':<10}  Filename"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for d in docs:
        icon = _status_icon(d["status"])
        age = _age(d.get("uploaded_at", ""))
        size = _human_size(d.get("file_size_bytes", 0))
        print(
            f"  {d['id']:>5}  {icon} {d['status']:<5}  {d.get('total_chunks', 0):>6}  "
            f"{size:>10}  {d.get('format', '?'):<10}  {age:<10}  {d.get('original_filename', '?')}"
        )


def _print_single(doc: dict):
    print(f"Document ID:  {doc['document_id']}")
    print(f"Title:        {doc['title']}")
    print(f"Filename:     {doc['original_filename']}")
    print(f"Format:       {doc['format']}")
    print(f"Status:       {_status_icon(doc['status'])} {doc['status']}")
    print(f"Size:         {_human_size(doc.get('file_size_bytes', 0))}")
    print(f"Chunks:       {doc['total_chunks']}")
    print(f"Uploaded at:  {doc.get('uploaded_at', '—')}  ({_age(doc.get('uploaded_at', ''))})")
    if doc.get("indexed_at"):
        print(f"Indexed at:   {doc['indexed_at']}  ({_age(doc['indexed_at'])})")
    if doc.get("error_message"):
        print(f"Error:        {doc['error_message']}")


def _show(args):
    if args.id:
        doc = _fetch_single(args.api_url, args.id)
        _print_single(doc)
        return True

    docs = _fetch_documents(args.api_url)

    if args.product:
        docs = [d for d in docs if d.get("product_name", "").lower() == args.product.lower()]

    if args.status:
        allowed = {s.strip().lower() for s in args.status.split(",")}
        docs = [d for d in docs if d["status"] in allowed]

    _print_summary(docs)

    if args.status:
        _print_table(sorted(docs, key=lambda d: d["id"]))
    else:
        for group_name, group_status in [("ERRORS", "error"), ("PROCESSING", "processing"), ("PENDING", "pending"), ("READY", "ready")]:
            group = [d for d in docs if d["status"] == group_status]
            if not group:
                continue
            print(f"--- {group_name} ({len(group)}) ---")
            show = group if group_status in ("error", "processing") else group[:20]
            _print_table(sorted(show, key=lambda d: d["id"]))
            if len(group) > len(show):
                print(f"  ... and {len(group) - len(show)} more (use --status {group_status} to see all)")
            print()

    has_active = any(d["status"] in ("pending", "processing") for d in docs)
    return has_active


def main():
    parser = argparse.ArgumentParser(
        description="Check document ingestion status in Lexiro.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  %(prog)s                              # full summary\n"
               "  %(prog)s --product 'Axxon One'        # filter by product\n"
               "  %(prog)s --status error               # only errors\n"
               "  %(prog)s --id 42                      # single document\n"
               "  %(prog)s --product 'Axxon One' --watch # poll until done\n",
    )
    parser.add_argument("--id", type=int, help="Show details for a single document by ID")
    parser.add_argument("--product", help="Filter by product name (case-insensitive)")
    parser.add_argument("--status", help="Filter by status (comma-separated: ready,pending,processing,error)")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL (default: http://localhost:8000)")
    parser.add_argument("--watch", action="store_true", help="Poll every --interval seconds until no pending/processing documents remain")
    parser.add_argument("--interval", type=int, default=10, help="Poll interval in seconds for --watch mode (default: 10)")

    args = parser.parse_args()

    try:
        if args.watch:
            iteration = 0
            while True:
                if iteration > 0:
                    print(f"\n{'=' * 60}")
                    print(f"  Refreshing... ({time.strftime('%H:%M:%S')})")
                    print(f"{'=' * 60}\n")
                has_active = _show(args)
                if not has_active:
                    print("All documents processed. Done.")
                    break
                iteration += 1
                time.sleep(args.interval)
        else:
            _show(args)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(0)
    except requests.ConnectionError:
        print(f"ERROR: Cannot connect to {args.api_url}", file=sys.stderr)
        sys.exit(1)
    except requests.HTTPError as e:
        print(f"ERROR: HTTP {e.response.status_code} - {e.response.text}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
