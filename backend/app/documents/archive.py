"""Archive extraction utilities for ZIP, 7z, tar, and RAR formats."""

import os

from fastapi import HTTPException

ARCHIVE_ALLOWED_EXTENSIONS = {".md", ".json", ".yaml", ".yml", ".pdf", ".proto", ".txt", ".wsdl", ".xml"}

SUPPORTED_ARCHIVE_EXTENSIONS = {".zip", ".7z", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".rar"}


def _archive_ext(filename: str) -> str:
    """Return the normalised archive extension, handling compound extensions like .tar.gz."""
    lower = filename.lower()
    for compound in (".tar.gz", ".tar.bz2", ".tar.xz"):
        if lower.endswith(compound):
            return compound
    return os.path.splitext(lower)[1]


def extract_archive(file_data: bytes, filename: str) -> list[tuple[str, bytes]]:
    """Extract files from an archive.

    Returns list of (archive_path, file_bytes) tuples for supported inner files.
    Skips directories and hidden files (starting with '.').
    """
    ext = _archive_ext(filename)

    if ext == ".zip":
        return extract_zip(file_data)
    if ext == ".7z":
        return extract_7z(file_data)
    if ext in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz"):
        return extract_tar(file_data, ext)
    if ext == ".rar":
        return extract_rar(file_data)

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported archive format '{ext}'. Supported: {', '.join(sorted(SUPPORTED_ARCHIVE_EXTENSIONS))}",
    )


def _is_allowed_entry(arc_path: str) -> bool:
    """Check if an archive entry should be extracted (not hidden, supported extension)."""
    basename = os.path.basename(arc_path)
    if not basename or basename.startswith("."):
        return False
    return os.path.splitext(basename)[1].lower() in ARCHIVE_ALLOWED_EXTENSIONS


# ---------------------------------------------------------------------------
# ZIP
# ---------------------------------------------------------------------------

def extract_zip(file_data: bytes) -> list[tuple[str, bytes]]:
    """Extract supported files from a ZIP archive in memory."""
    import io
    import zipfile

    try:
        zf = zipfile.ZipFile(io.BytesIO(file_data))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")

    result = []
    for info in zf.infolist():
        if info.is_dir():
            continue
        if not _is_allowed_entry(info.filename):
            continue
        result.append((info.filename, zf.read(info.filename)))
    return result


# ---------------------------------------------------------------------------
# 7z
# ---------------------------------------------------------------------------

def extract_7z(file_data: bytes) -> list[tuple[str, bytes]]:
    """Extract supported files from a 7z archive in memory."""
    import io
    import tempfile

    try:
        import py7zr
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="7z support requires the py7zr package. Install it with: pip install py7zr",
        )

    try:
        archive = py7zr.SevenZipFile(io.BytesIO(file_data), mode="r")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid 7z file")

    result = []
    try:
        names = archive.getnames()
        if not names:
            return result

        with tempfile.TemporaryDirectory() as tmpdir:
            archive.extractall(path=tmpdir)
            for arc_path in names:
                if not _is_allowed_entry(arc_path):
                    continue
                full_path = os.path.join(tmpdir, arc_path)
                if os.path.isfile(full_path):
                    with open(full_path, "rb") as f:
                        result.append((arc_path, f.read()))
    finally:
        archive.close()

    return result


# ---------------------------------------------------------------------------
# tar family (.tar, .tar.gz, .tgz, .tar.bz2, .tar.xz)
# ---------------------------------------------------------------------------

_TAR_MODE_MAP = {
    ".tar": "r:",
    ".tar.gz": "r:gz",
    ".tgz": "r:gz",
    ".tar.bz2": "r:bz2",
    ".tar.xz": "r:xz",
}


def extract_tar(file_data: bytes, ext: str) -> list[tuple[str, bytes]]:
    """Extract supported files from a tar archive (optionally compressed)."""
    import io
    import tarfile

    mode = _TAR_MODE_MAP.get(ext, "r:*")

    try:
        tf = tarfile.open(fileobj=io.BytesIO(file_data), mode=mode)
    except (tarfile.TarError, Exception):
        raise HTTPException(status_code=400, detail=f"Invalid tar archive ({ext})")

    result = []
    try:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            if not _is_allowed_entry(member.name):
                continue
            extracted = tf.extractfile(member)
            if extracted is not None:
                result.append((member.name, extracted.read()))
    finally:
        tf.close()

    return result


# ---------------------------------------------------------------------------
# RAR
# ---------------------------------------------------------------------------

def extract_rar(file_data: bytes) -> list[tuple[str, bytes]]:
    """Extract supported files from a RAR archive."""
    import io
    import tempfile

    try:
        import rarfile
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="RAR support requires the rarfile package. Install it with: pip install rarfile",
        )

    with tempfile.NamedTemporaryFile(suffix=".rar", delete=False) as tmp:
        tmp.write(file_data)
        tmp_path = tmp.name

    try:
        try:
            rf = rarfile.RarFile(tmp_path)
        except (rarfile.BadRarFile, rarfile.NotRarFile, Exception):
            raise HTTPException(status_code=400, detail="Invalid RAR file")

        result = []
        try:
            for info in rf.infolist():
                if info.is_dir():
                    continue
                if not _is_allowed_entry(info.filename):
                    continue
                result.append((info.filename, rf.read(info.filename)))
        finally:
            rf.close()

        return result
    finally:
        os.unlink(tmp_path)
