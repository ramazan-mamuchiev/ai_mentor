"""Tests for PDF/OCR converter (migrated from doc2md-mcp).

Tests cover: IMG_REF_RE regex, ocr_image_file, _find_ocr_pages,
enrich_markdown_with_ocr_files, and the main convert_pdf function.
"""

import os
from unittest.mock import patch

import pymupdf
import pytest

from app.ingestion.converters.pdf import (
    _find_ocr_pages,
    convert_pdf,
)
from app.ingestion.converters.ocr import (
    IMG_REF_RE,
    OCR_IMAGE_MIN_AREA,
    enrich_markdown_with_ocr_files,
    ocr_image_file,
)


# ---------------------------------------------------------------------------
# _IMG_REF_RE — regex correctness
# ---------------------------------------------------------------------------

class TestImgRefRegex:
    def test_simple_path(self):
        md = "![alt](images/photo.png)"
        m = IMG_REF_RE.search(md)
        assert m is not None
        assert m.group(2) == "images/photo.png"

    def test_path_with_single_parens(self):
        md = "![](D:/docs/Guide_V2.6.1(2)/img.png)"
        m = IMG_REF_RE.search(md)
        assert m is not None
        assert m.group(2) == "D:/docs/Guide_V2.6.1(2)/img.png"

    def test_path_with_multiple_parens(self):
        md = "![](D:/export/Name (copy)/V2.6.1(2)-file.pdf-0-full.png)"
        m = IMG_REF_RE.search(md)
        assert m is not None
        assert m.group(2) == "D:/export/Name (copy)/V2.6.1(2)-file.pdf-0-full.png"

    def test_path_with_spaces_and_parens(self):
        md = "![x](C:/My Folder (1)/sub dir (test)/image(3).png)"
        m = IMG_REF_RE.search(md)
        assert m is not None
        assert m.group(2) == "C:/My Folder (1)/sub dir (test)/image(3).png"

    def test_multiple_refs_same_line(self):
        md = "![a](dir(1)/a.png) text ![b](dir(2)/b.png)"
        matches = IMG_REF_RE.findall(md)
        assert len(matches) == 2
        assert matches[0][1] == "dir(1)/a.png"
        assert matches[1][1] == "dir(2)/b.png"

    def test_no_parens_in_path(self):
        md = "![](simple/path/image.png)"
        m = IMG_REF_RE.search(md)
        assert m is not None
        assert m.group(2) == "simple/path/image.png"

    def test_empty_alt_text(self):
        md = "![](path(x)/img.png)"
        m = IMG_REF_RE.search(md)
        assert m is not None
        assert m.group(1) == ""
        assert m.group(2) == "path(x)/img.png"


# ---------------------------------------------------------------------------
# _ocr_image_file — PIL-based reading (non-ASCII path support)
# ---------------------------------------------------------------------------

class TestOcrImageFile:
    def _make_white_png(self, path):
        from PIL import Image
        img = Image.new("RGB", (100, 50), (255, 255, 255))
        img.save(str(path))

    def test_non_ascii_path(self, tmp_path):
        subdir = tmp_path / "C#\xa0Access\xa0Demo"
        subdir.mkdir()
        img = subdir / "test.png"
        self._make_white_png(img)

        with patch("app.ingestion.converters.ocr.get_ocr_reader") as mock_reader:
            mock_reader.return_value.readtext.return_value = [
                (None, "hello", 0.9),
            ]
            result = ocr_image_file(str(img), ["en"])

        assert result == "hello"

    def test_path_with_parentheses(self, tmp_path):
        subdir = tmp_path / "Guide(v2)"
        subdir.mkdir()
        img = subdir / "img(0).png"
        self._make_white_png(img)

        with patch("app.ingestion.converters.ocr.get_ocr_reader") as mock_reader:
            mock_reader.return_value.readtext.return_value = [
                (None, "world", 0.95),
            ]
            result = ocr_image_file(str(img), ["en"])

        assert result == "world"

    def test_path_with_spaces(self, tmp_path):
        subdir = tmp_path / "My Documents"
        subdir.mkdir()
        img = subdir / "photo.png"
        self._make_white_png(img)

        with patch("app.ingestion.converters.ocr.get_ocr_reader") as mock_reader:
            mock_reader.return_value.readtext.return_value = []
            result = ocr_image_file(str(img), ["en"])

        assert result == ""


# ---------------------------------------------------------------------------
# _find_ocr_pages — page-level OCR detection by image area
# ---------------------------------------------------------------------------

class TestFindOcrPages:
    def test_returns_pages_with_large_images(self, tmp_path):
        from PIL import Image

        pdf_path = str(tmp_path / "test.pdf")
        img_path = str(tmp_path / "large.png")
        Image.new("RGB", (400, 400), (128, 128, 128)).save(img_path)

        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        page.insert_image(pymupdf.Rect(50, 50, 450, 450), filename=img_path)
        doc.save(pdf_path)
        doc.close()

        result = _find_ocr_pages(pdf_path)
        assert result == [0], f"Expected [0] for 400x400 image (160000 px), got {result}"

    def test_skips_pages_with_small_images(self, tmp_path):
        from PIL import Image

        pdf_path = str(tmp_path / "test.pdf")
        img_path = str(tmp_path / "small.png")
        Image.new("RGB", (50, 50), (200, 200, 200)).save(img_path)

        doc = pymupdf.open()
        page = doc.new_page(width=612, height=792)
        page.insert_image(pymupdf.Rect(50, 50, 100, 100), filename=img_path)
        doc.save(pdf_path)
        doc.close()

        result = _find_ocr_pages(pdf_path)
        assert result == [], f"Expected [] for 50x50 image (2500 px), got {result}"

    def test_empty_pdf(self, tmp_path):
        pdf_path = str(tmp_path / "empty.pdf")
        doc = pymupdf.open()
        doc.new_page(width=612, height=792)
        doc.save(pdf_path)
        doc.close()

        result = _find_ocr_pages(pdf_path)
        assert result == []

    def test_mixed_pages(self, tmp_path):
        from PIL import Image

        pdf_path = str(tmp_path / "mixed.pdf")
        img_large_path = str(tmp_path / "large.png")
        img_small_path = str(tmp_path / "small.png")
        Image.new("RGB", (500, 500), (100, 100, 100)).save(img_large_path)
        Image.new("RGB", (20, 20), (50, 50, 50)).save(img_small_path)

        doc = pymupdf.open()
        doc.new_page(width=612, height=792)

        page1 = doc.new_page(width=612, height=792)
        page1.insert_image(pymupdf.Rect(10, 10, 510, 510), filename=img_large_path)

        page2 = doc.new_page(width=612, height=792)
        page2.insert_image(pymupdf.Rect(10, 10, 30, 30), filename=img_small_path)

        doc.save(pdf_path)
        doc.close()

        result = _find_ocr_pages(pdf_path)
        assert result == [1], f"Expected [1] (only page with 500x500 image), got {result}"


# ---------------------------------------------------------------------------
# enrich_markdown_with_ocr_files
# ---------------------------------------------------------------------------

class TestEnrichMarkdownWithOcrFiles:
    def test_replaces_image_with_ocr_text(self, tmp_path):
        img = tmp_path / "diagram.png"
        img.touch()
        md = f"Before\n![alt]({img})\nAfter"

        with patch("app.ingestion.converters.ocr.ocr_image_file", return_value="recognized text"), \
             patch("app.ingestion.converters.ocr.get_ocr_reader"):
            result, stats = enrich_markdown_with_ocr_files(md, ["en"])

        assert "recognized text" in result
        assert "![alt]" not in result
        assert stats["ocr_images_success"] == 1
        assert stats["ocr_images_total"] == 1

    def test_file_not_found(self):
        md = "![alt](/nonexistent/image.png)"
        with patch("app.ingestion.converters.ocr.get_ocr_reader"):
            result, stats = enrich_markdown_with_ocr_files(md, ["en"])
        assert "![alt]" not in result
        assert stats["ocr_images_success"] == 0
        assert stats["ocr_images_failed"] == 1

    def test_empty_ocr_result(self, tmp_path):
        img = tmp_path / "empty.png"
        img.touch()
        md = f"Text\n![x]({img})\nMore"

        with patch("app.ingestion.converters.ocr.ocr_image_file", return_value="   "), \
             patch("app.ingestion.converters.ocr.get_ocr_reader"):
            result, stats = enrich_markdown_with_ocr_files(md, ["en"])

        assert "![x]" not in result
        assert stats["ocr_images_success"] == 0
        assert stats["ocr_images_empty"] == 1

    def test_ocr_exception(self, tmp_path):
        img = tmp_path / "bad.png"
        img.touch()
        md = f"![x]({img})"

        with patch("app.ingestion.converters.ocr.ocr_image_file", side_effect=RuntimeError("OCR crashed")), \
             patch("app.ingestion.converters.ocr.get_ocr_reader"):
            result, stats = enrich_markdown_with_ocr_files(md, ["en"])

        assert "![x]" not in result
        assert stats["ocr_images_success"] == 0
        assert stats["ocr_images_failed"] == 1

    def test_no_images(self):
        md = "Just plain text\nwith no images"
        result, stats = enrich_markdown_with_ocr_files(md, ["en"])
        assert result == md
        assert stats["ocr_images_total"] == 0

    def test_multiple_images(self, tmp_path):
        img1 = tmp_path / "a.png"
        img2 = tmp_path / "b.png"
        img1.touch()
        img2.touch()
        md = f"![first]({img1})\nMiddle\n![second]({img2})"

        def mock_ocr(path, langs=None):
            if "a.png" in path:
                return "alpha text"
            return "beta text"

        with patch("app.ingestion.converters.ocr.ocr_image_file", side_effect=mock_ocr), \
             patch("app.ingestion.converters.ocr.get_ocr_reader"):
            result, stats = enrich_markdown_with_ocr_files(md, ["en"])

        assert "alpha text" in result
        assert "beta text" in result
        assert stats["ocr_images_success"] == 2
        assert stats["ocr_images_total"] == 2

    def test_path_with_parentheses(self, tmp_path):
        subdir = tmp_path / "Guide_V2.6.1(2)"
        subdir.mkdir()
        img = subdir / "image(0).png"
        img.touch()
        md = f"Text\n![alt]({img})\nEnd"

        with patch("app.ingestion.converters.ocr.ocr_image_file", return_value="found text"), \
             patch("app.ingestion.converters.ocr.get_ocr_reader"):
            result, stats = enrich_markdown_with_ocr_files(md, ["en"])

        assert "found text" in result
        assert "![alt]" not in result
        assert stats["ocr_images_total"] == 1
        assert stats["ocr_images_success"] == 1
        assert stats["ocr_images_failed"] == 0

    def test_skips_small_images(self, tmp_path):
        from PIL import Image

        small_img = tmp_path / "tiny.png"
        Image.new("RGB", (20, 20), (255, 255, 255)).save(str(small_img))

        large_img = tmp_path / "big.png"
        Image.new("RGB", (400, 400), (128, 128, 128)).save(str(large_img))

        md = f"![small]({small_img})\n![big]({large_img})"

        with patch("app.ingestion.converters.ocr.ocr_image_file", return_value="big text"), \
             patch("app.ingestion.converters.ocr.get_ocr_reader"):
            result, stats = enrich_markdown_with_ocr_files(md, ["en"])

        assert stats["ocr_images_total"] == 2
        assert stats["ocr_images_empty"] == 1
        assert stats["ocr_images_success"] == 1
        assert "big text" in result
        assert "![small]" not in result
        assert "![big]" not in result

    def test_all_small_images_skipped(self, tmp_path):
        from PIL import Image

        img1 = tmp_path / "icon1.png"
        img2 = tmp_path / "icon2.png"
        Image.new("RGB", (10, 10), (255, 0, 0)).save(str(img1))
        Image.new("RGB", (30, 30), (0, 255, 0)).save(str(img2))

        md = f"Text\n![a]({img1})\n![b]({img2})\nEnd"

        with patch("app.ingestion.converters.ocr.ocr_image_file") as mock_ocr, \
             patch("app.ingestion.converters.ocr.get_ocr_reader"):
            result, stats = enrich_markdown_with_ocr_files(md, ["en"])

        mock_ocr.assert_not_called()
        assert stats["ocr_images_total"] == 2
        assert stats["ocr_images_empty"] == 2
        assert stats["ocr_images_success"] == 0


# ---------------------------------------------------------------------------
# convert_pdf — main entry point
# ---------------------------------------------------------------------------

class TestConvertPdf:
    def test_text_pdf_conversion(self, sample_text_pdf):
        md_text, meta = convert_pdf(str(sample_text_pdf))
        assert "Chapter 1" in md_text or "Introduction" in md_text
        assert meta["pages"] == 2
        assert meta["total_ms"] > 0

    def test_metadata_fields(self, sample_text_pdf):
        _, meta = convert_pdf(str(sample_text_pdf))
        assert "pages" in meta
        assert "file_size_bytes" in meta
        assert "convert_ms" in meta
        assert "total_ms" in meta

    def test_no_ocr_when_no_images(self, sample_text_pdf):
        md_text, meta = convert_pdf(str(sample_text_pdf))
        assert meta["ocr_applied"] is False

    def test_no_ocr_when_easyocr_unavailable(self, sample_image_pdf):
        with patch("app.ingestion.converters.ocr.ocr_enabled", return_value=False):
            md_text, meta = convert_pdf(str(sample_image_pdf))
        assert meta["ocr_applied"] is False
