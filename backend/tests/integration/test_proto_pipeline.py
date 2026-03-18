"""Integration tests for proto -> markdown conversion through the ingestion pipeline."""

import os
import tempfile

import pytest
from sqlalchemy import select

from app.ingestion.converters.proto import convert_proto, convert_proto_file
from app.ingestion.pipeline import detect_format, ingest_file
from app.models import Chunk, Document, Product


SAMPLE_PROTO = """\
syntax = "proto3";

package test.api.v1;

service TestService {
  rpc GetItem(GetItemRequest) returns (GetItemResponse);
  rpc ListItems(ListItemsRequest) returns (stream Item);
}

message GetItemRequest {
  string id = 1;
}

message GetItemResponse {
  Item item = 1;
}

message ListItemsRequest {
  int32 page_size = 1;
  string page_token = 2;
}

message Item {
  string id = 1;
  string name = 2;
  ItemType type = 3;
}

enum ItemType {
  ITEM_TYPE_UNSPECIFIED = 0;
  ITEM_TYPE_DEVICE = 1;
  ITEM_TYPE_SENSOR = 2;
}
"""


class TestDetectFormat:
    def test_proto_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".proto", delete=False, mode="w") as f:
            f.write(SAMPLE_PROTO)
            f.flush()
            try:
                assert detect_format(f.name) == "proto"
            finally:
                os.unlink(f.name)


class TestConvertProtoFile:
    def test_file_conversion(self):
        with tempfile.NamedTemporaryFile(
            suffix=".proto", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write(SAMPLE_PROTO)
            f.flush()
            try:
                md, meta = convert_proto_file(f.name)
                assert "## Service `TestService`" in md
                assert "### Message `GetItemRequest`" in md
                assert "### Enum `ItemType`" in md
                assert meta["services"] == 1
                assert meta["methods"] == 2
                assert meta["messages"] >= 4
                assert meta["enums"] == 1
            finally:
                os.unlink(f.name)


class TestConvertProtoMarkdownQuality:
    """Verify that the Markdown output is suitable for semantic search."""

    def test_contains_natural_language_descriptions(self):
        md, _ = convert_proto(SAMPLE_PROTO)
        assert "Service" in md
        assert "Message" in md
        assert "Field" in md

    def test_method_signatures_readable(self):
        md, _ = convert_proto(SAMPLE_PROTO)
        assert "rpc GetItem(GetItemRequest) returns (GetItemResponse)" in md
        assert "stream Item" in md

    def test_field_table_structure(self):
        md, _ = convert_proto(SAMPLE_PROTO)
        assert "| # | Field | Type | Label | Description |" in md
        assert "`id`" in md
        assert "`string`" in md

    def test_enum_values_listed(self):
        md, _ = convert_proto(SAMPLE_PROTO)
        assert "`ITEM_TYPE_DEVICE`" in md
        assert "`ITEM_TYPE_SENSOR`" in md


@pytest.mark.usefixtures("_init_schema", "mock_embedder")
class TestProtoIngestionPipeline:
    """Integration test: ingest a .proto file through the full pipeline."""

    async def test_ingest_proto_file(self, db_session):
        with tempfile.NamedTemporaryFile(
            suffix=".proto", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write(SAMPLE_PROTO)
            f.flush()
            proto_path = f.name

        try:
            result = await ingest_file(
                session=db_session,
                file_path=proto_path,
                product_name="TestProtoProduct",
                firmware_version="1.0",
                manufacturer="TestMfg",
            )

            assert result["status"] == "ok"
            assert result["chunks"] > 0
            assert result["format"] == "proto"
            assert result["product"] == "TestProtoProduct"

            product = (await db_session.execute(
                select(Product).where(Product.name == "TestProtoProduct")
            )).scalar_one()
            assert product.manufacturer == "TestMfg"

            doc = (await db_session.execute(
                select(Document).where(Document.product_id == product.id)
            )).scalar_one()
            assert doc.status == "ready"
            assert doc.total_chunks > 0

            chunks = (await db_session.execute(
                select(Chunk).where(Chunk.document_id == doc.id)
            )).scalars().all()
            assert len(chunks) > 0

            all_content = " ".join(c.content for c in chunks)
            assert "TestService" in all_content
            assert "GetItem" in all_content

        finally:
            os.unlink(proto_path)

    async def test_proto_dedup(self, db_session):
        """Same proto file ingested twice should be skipped."""
        with tempfile.NamedTemporaryFile(
            suffix=".proto", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write(SAMPLE_PROTO)
            f.flush()
            proto_path = f.name

        try:
            r1 = await ingest_file(
                session=db_session,
                file_path=proto_path,
                product_name="DedupProtoProduct",
                firmware_version="1.0",
            )
            assert r1["status"] == "ok"

            r2 = await ingest_file(
                session=db_session,
                file_path=proto_path,
                product_name="DedupProtoProduct",
                firmware_version="1.0",
            )
            assert r2["status"] == "skipped"
        finally:
            os.unlink(proto_path)
