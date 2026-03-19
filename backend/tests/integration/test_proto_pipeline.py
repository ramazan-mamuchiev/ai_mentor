"""Integration tests for proto -> markdown conversion through the ingestion pipeline."""

import os
import tempfile

import pytest
from sqlalchemy import select

from app.ingestion.converters.proto import convert_proto, convert_proto_file
from app.ingestion.pipeline import detect_format, ingest_file
from app.models import Chunk, Document, Product


def _write_proto(content: str) -> str:
    """Write proto content to a temp file and return its path (Windows-safe)."""
    fd, path = tempfile.mkstemp(suffix=".proto")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


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
        path = _write_proto(SAMPLE_PROTO)
        try:
            assert detect_format(path) == "proto"
        finally:
            os.unlink(path)


class TestConvertProtoFile:
    def test_file_conversion(self):
        path = _write_proto(SAMPLE_PROTO)
        try:
            md, meta = convert_proto_file(path)
            assert "## Service `TestService`" in md
            assert "### Message `GetItemRequest`" in md
            assert "### Enum `ItemType`" in md
            assert meta["services"] == 1
            assert meta["methods"] == 2
            assert meta["messages"] >= 4
            assert meta["enums"] == 1
        finally:
            os.unlink(path)


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


def _all_chunk_text(chunks) -> str:
    """Combine heading_path + content from all chunks for assertion checks."""
    return " ".join(f"{c.heading_path} {c.content}" for c in chunks)


@pytest.mark.usefixtures("_init_schema")
class TestProtoIngestionPipeline:
    """Integration test: ingest a .proto file through the full pipeline."""

    async def test_ingest_proto_file(self, db_session):
        proto_path = _write_proto(SAMPLE_PROTO)

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

            all_text = _all_chunk_text(chunks)
            assert "GetItem" in all_text
            assert "GetItemRequest" in all_text

        finally:
            os.unlink(proto_path)

    async def test_proto_dedup(self, db_session):
        """Same proto file ingested twice should be skipped."""
        proto_path = _write_proto(SAMPLE_PROTO)

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


# ---------------------------------------------------------------------------
# Allman-style proto integration tests
# ---------------------------------------------------------------------------

ALLMAN_PROTO = """\
syntax = "proto3";

package axxonsoft.bl.acfa;

import "google/protobuf/wrappers.proto";

service AcfaService
{
    rpc ListUnitsEvents(ListUnitsEventsRequest) returns (stream ListUnitsEventsResponse);
    rpc PerformAction(PerformActionRequest) returns (PerformActionResponse);
}

message ListUnitsEventsRequest
{
    message Unit
    {
        string uid = 1;
    }

    repeated Unit items = 1;
    int32 portion_size = 2;
}

message ListUnitsEventsResponse
{
    message UnitEvents
    {
        string uid = 1;
        repeated string events = 2;
    }

    repeated UnitEvents items = 1;
    bool more_data = 2;
}

message PerformActionRequest
{
    string unit_uid = 1;
    string action_id = 2;
}

message PerformActionResponse
{
    bool success = 1;
    string error_message = 2;
}

enum EStatesMode
{
    SM_ALL = 0;
    SM_CURRENT = 1;
}
"""


class TestConvertAllmanProtoFile:
    """Integration: convert_proto_file with Allman-style content."""

    def test_allman_file_conversion(self):
        path = _write_proto(ALLMAN_PROTO)
        try:
            md, meta = convert_proto_file(path)
            assert "## Service `AcfaService`" in md
            assert "### Message `ListUnitsEventsRequest`" in md
            assert "### Message `ListUnitsEventsResponse`" in md
            assert "### Enum `EStatesMode`" in md
            assert meta["services"] == 1
            assert meta["methods"] == 2
            assert meta["messages"] >= 4
            assert meta["enums"] == 1
        finally:
            os.unlink(path)

    def test_allman_file_with_original_filename(self):
        path = _write_proto(ALLMAN_PROTO)
        try:
            md, meta = convert_proto_file(
                path, original_filename="AcfaService.proto"
            )
            assert "# AcfaService.proto" in md
            assert os.path.basename(path) not in md
        finally:
            os.unlink(path)


class TestAllmanProtoMarkdownQuality:
    """Verify that Allman-style proto Markdown output is suitable for semantic search."""

    def test_contains_service_and_methods(self):
        md, _ = convert_proto(ALLMAN_PROTO, "AcfaService.proto")
        assert "## Service `AcfaService`" in md
        assert "rpc ListUnitsEvents" in md
        assert "rpc PerformAction" in md

    def test_contains_all_messages(self):
        md, _ = convert_proto(ALLMAN_PROTO, "AcfaService.proto")
        assert "### Message `ListUnitsEventsRequest`" in md
        assert "### Message `ListUnitsEventsResponse`" in md
        assert "### Message `PerformActionRequest`" in md
        assert "### Message `PerformActionResponse`" in md

    def test_contains_enum(self):
        md, _ = convert_proto(ALLMAN_PROTO, "AcfaService.proto")
        assert "### Enum `EStatesMode`" in md
        assert "`SM_ALL`" in md
        assert "`SM_CURRENT`" in md

    def test_contains_nested_message(self):
        md, _ = convert_proto(ALLMAN_PROTO, "AcfaService.proto")
        assert "Unit" in md

    def test_field_tables_present(self):
        md, _ = convert_proto(ALLMAN_PROTO, "AcfaService.proto")
        assert "| # | Field | Type | Label | Description |" in md
        assert "`items`" in md
        assert "`more_data`" in md

    def test_streaming_annotation(self):
        md, _ = convert_proto(ALLMAN_PROTO, "AcfaService.proto")
        assert "stream ListUnitsEventsResponse" in md


class TestDetectFormatAllman:
    """Integration: detect_format correctly identifies Allman-style .proto files."""

    def test_allman_proto_detected(self):
        path = _write_proto(ALLMAN_PROTO)
        try:
            assert detect_format(path) == "proto"
        finally:
            os.unlink(path)

    def test_detect_format_by_original_filename(self):
        """detect_format uses extension, so passing original_filename with .proto works."""
        assert detect_format("AcfaService.proto") == "proto"
        assert detect_format("some/path/to/Service.proto") == "proto"


@pytest.mark.usefixtures("_init_schema")
class TestAllmanProtoIngestionPipeline:
    """Integration test: ingest an Allman-style .proto file through the full pipeline."""

    async def test_ingest_allman_proto(self, db_session):
        proto_path = _write_proto(ALLMAN_PROTO)

        try:
            result = await ingest_file(
                session=db_session,
                file_path=proto_path,
                product_name="AllmanProtoProduct",
                firmware_version="1.0",
                manufacturer="AxxonSoft",
            )

            assert result["status"] == "ok"
            assert result["chunks"] > 1, (
                f"Allman proto should produce >1 chunk, got {result['chunks']}"
            )
            assert result["format"] == "proto"
            assert result["product"] == "AllmanProtoProduct"

            product = (await db_session.execute(
                select(Product).where(Product.name == "AllmanProtoProduct")
            )).scalar_one()
            assert product.manufacturer == "AxxonSoft"

            doc = (await db_session.execute(
                select(Document).where(Document.product_id == product.id)
            )).scalar_one()
            assert doc.status == "ready"
            assert doc.total_chunks > 1

            chunks = (await db_session.execute(
                select(Chunk).where(Chunk.document_id == doc.id)
            )).scalars().all()
            assert len(chunks) > 1

            all_text = _all_chunk_text(chunks)
            assert "ListUnitsEventsResponse" in all_text
            assert "ListUnitsEventsRequest" in all_text
            assert "rpc ListUnitsEvents" in all_text

        finally:
            os.unlink(proto_path)

    async def test_allman_proto_chunks_have_correct_headings(self, db_session):
        """Chunk heading_path should reference proto elements, not temp filenames."""
        proto_path = _write_proto(ALLMAN_PROTO)

        try:
            result = await ingest_file(
                session=db_session,
                file_path=proto_path,
                product_name="AllmanHeadingProduct",
                firmware_version="1.0",
            )
            assert result["status"] == "ok"

            product = (await db_session.execute(
                select(Product).where(Product.name == "AllmanHeadingProduct")
            )).scalar_one()
            doc = (await db_session.execute(
                select(Document).where(Document.product_id == product.id)
            )).scalar_one()
            chunks = (await db_session.execute(
                select(Chunk).where(Chunk.document_id == doc.id)
            )).scalars().all()

            all_headings = [c.heading_path for c in chunks]
            heading_text = " ".join(all_headings)
            assert "Service" in heading_text or "Message" in heading_text or "Enum" in heading_text

        finally:
            os.unlink(proto_path)

    async def test_allman_proto_dedup(self, db_session):
        """Same Allman proto ingested twice should be skipped."""
        proto_path = _write_proto(ALLMAN_PROTO)

        try:
            r1 = await ingest_file(
                session=db_session,
                file_path=proto_path,
                product_name="AllmanDedupProduct",
                firmware_version="1.0",
            )
            assert r1["status"] == "ok"

            r2 = await ingest_file(
                session=db_session,
                file_path=proto_path,
                product_name="AllmanDedupProduct",
                firmware_version="1.0",
            )
            assert r2["status"] == "skipped"
        finally:
            os.unlink(proto_path)

    async def test_allman_proto_enum_in_chunks(self, db_session):
        """Enum values from Allman-style proto should appear in chunks."""
        proto_path = _write_proto(ALLMAN_PROTO)

        try:
            result = await ingest_file(
                session=db_session,
                file_path=proto_path,
                product_name="AllmanEnumProduct",
                firmware_version="1.0",
            )
            assert result["status"] == "ok"

            product = (await db_session.execute(
                select(Product).where(Product.name == "AllmanEnumProduct")
            )).scalar_one()
            doc = (await db_session.execute(
                select(Document).where(Document.product_id == product.id)
            )).scalar_one()
            chunks = (await db_session.execute(
                select(Chunk).where(Chunk.document_id == doc.id)
            )).scalars().all()

            all_text = _all_chunk_text(chunks)
            assert "EStatesMode" in all_text
            assert "SM_ALL" in all_text

        finally:
            os.unlink(proto_path)


# ---------------------------------------------------------------------------
# Mixed K&R + Allman integration
# ---------------------------------------------------------------------------

MIXED_STYLE_PROTO = """\
syntax = "proto3";
package test.mixed;

service MixedService {
    rpc GetData(GetDataRequest) returns (GetDataResponse);
}

message GetDataRequest
{
    string id = 1;
}

message GetDataResponse {
    string data = 1;
    int32 code = 2;
}

enum Status
{
    STATUS_UNKNOWN = 0;
    STATUS_OK = 1;
}
"""


@pytest.mark.usefixtures("_init_schema")
class TestMixedStyleProtoIngestion:
    """Integration: proto files mixing K&R and Allman brace styles."""

    async def test_mixed_style_ingestion(self, db_session):
        proto_path = _write_proto(MIXED_STYLE_PROTO)

        try:
            result = await ingest_file(
                session=db_session,
                file_path=proto_path,
                product_name="MixedStyleProduct",
                firmware_version="1.0",
            )
            assert result["status"] == "ok"
            assert result["chunks"] > 1

            product = (await db_session.execute(
                select(Product).where(Product.name == "MixedStyleProduct")
            )).scalar_one()
            doc = (await db_session.execute(
                select(Document).where(Document.product_id == product.id)
            )).scalar_one()
            chunks = (await db_session.execute(
                select(Chunk).where(Chunk.document_id == doc.id)
            )).scalars().all()

            all_text = _all_chunk_text(chunks)
            assert "GetDataRequest" in all_text
            assert "GetDataResponse" in all_text
            assert "rpc GetData" in all_text
            assert "STATUS_OK" in all_text

        finally:
            os.unlink(proto_path)
