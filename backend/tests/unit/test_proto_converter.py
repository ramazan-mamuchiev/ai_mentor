"""Unit tests for proto -> markdown converter."""

import pytest

from app.ingestion.converters.proto import (
    ProtoEnum,
    ProtoField,
    ProtoFile,
    ProtoMessage,
    ProtoMethod,
    ProtoService,
    convert_proto,
    parse_proto,
)


SAMPLE_PROTO = """\
syntax = "proto3";

package axxon.domophone.v1;

import "google/protobuf/timestamp.proto";
import "google/protobuf/empty.proto";

option go_package = "axxon/domophone/v1";

// DomophoneService manages intercom devices.
// Provides methods for door control and event streaming.
service DomophoneService {
  // Open a door lock remotely.
  rpc OpenDoor(OpenDoorRequest) returns (OpenDoorResponse);

  // Stream real-time events from the intercom.
  rpc StreamEvents(StreamEventsRequest) returns (stream DomophoneEvent);

  // Bidirectional audio channel.
  rpc AudioChannel(stream AudioFrame) returns (stream AudioFrame);
}

// Request to open a specific door.
message OpenDoorRequest {
  string device_id = 1;  // Unique device identifier
  int32 door_number = 2; // Door index (1-based)
  uint32 hold_time_ms = 3;
}

message OpenDoorResponse {
  bool success = 1;
  string error_message = 2;
}

message StreamEventsRequest {
  string device_id = 1;
  repeated string event_types = 2;
}

message DomophoneEvent {
  string event_id = 1;
  EventType type = 2;
  google.protobuf.Timestamp timestamp = 3;
  string device_id = 4;

  oneof payload {
    DoorOpenEvent door_open = 10;
    CallEvent call = 11;
    MotionEvent motion = 12;
  }
}

// Types of domophone events.
enum EventType {
  EVENT_TYPE_UNSPECIFIED = 0;
  EVENT_TYPE_DOOR_OPEN = 1;
  EVENT_TYPE_CALL = 2;
  EVENT_TYPE_MOTION = 3;
}

message DoorOpenEvent {
  int32 door_number = 1;
  string opened_by = 2;
}

message CallEvent {
  string caller_id = 1;
  int32 apartment = 2;
}

message MotionEvent {
  string zone = 1;
  float confidence = 2;
}

message AudioFrame {
  bytes data = 1;
  int32 sample_rate = 2;
}
"""


class TestParseProto:
    def test_syntax(self):
        result = parse_proto(SAMPLE_PROTO)
        assert result.syntax == "proto3"

    def test_package(self):
        result = parse_proto(SAMPLE_PROTO)
        assert result.package == "axxon.domophone.v1"

    def test_imports(self):
        result = parse_proto(SAMPLE_PROTO)
        assert "google/protobuf/timestamp.proto" in result.imports
        assert "google/protobuf/empty.proto" in result.imports

    def test_options(self):
        result = parse_proto(SAMPLE_PROTO)
        assert result.options.get("go_package") == "axxon/domophone/v1"

    def test_service_count(self):
        result = parse_proto(SAMPLE_PROTO)
        assert len(result.services) == 1

    def test_service_name(self):
        result = parse_proto(SAMPLE_PROTO)
        svc = result.services[0]
        assert svc.name == "DomophoneService"

    def test_service_methods(self):
        result = parse_proto(SAMPLE_PROTO)
        svc = result.services[0]
        assert len(svc.methods) == 3
        names = [m.name for m in svc.methods]
        assert "OpenDoor" in names
        assert "StreamEvents" in names
        assert "AudioChannel" in names

    def test_method_streaming(self):
        result = parse_proto(SAMPLE_PROTO)
        svc = result.services[0]
        methods = {m.name: m for m in svc.methods}

        open_door = methods["OpenDoor"]
        assert not open_door.client_streaming
        assert not open_door.server_streaming

        stream_events = methods["StreamEvents"]
        assert not stream_events.client_streaming
        assert stream_events.server_streaming

        audio = methods["AudioChannel"]
        assert audio.client_streaming
        assert audio.server_streaming

    def test_method_types(self):
        result = parse_proto(SAMPLE_PROTO)
        svc = result.services[0]
        methods = {m.name: m for m in svc.methods}

        assert methods["OpenDoor"].input_type == "OpenDoorRequest"
        assert methods["OpenDoor"].output_type == "OpenDoorResponse"

    def test_message_count(self):
        result = parse_proto(SAMPLE_PROTO)
        assert len(result.messages) >= 7

    def test_message_fields(self):
        result = parse_proto(SAMPLE_PROTO)
        msgs = {m.name: m for m in result.messages}

        req = msgs["OpenDoorRequest"]
        assert len(req.fields) == 3
        field_names = [f.name for f in req.fields]
        assert "device_id" in field_names
        assert "door_number" in field_names
        assert "hold_time_ms" in field_names

    def test_field_types(self):
        result = parse_proto(SAMPLE_PROTO)
        msgs = {m.name: m for m in result.messages}
        req = msgs["OpenDoorRequest"]
        fields = {f.name: f for f in req.fields}
        assert fields["device_id"].type == "string"
        assert fields["door_number"].type == "int32"
        assert fields["hold_time_ms"].type == "uint32"

    def test_field_numbers(self):
        result = parse_proto(SAMPLE_PROTO)
        msgs = {m.name: m for m in result.messages}
        req = msgs["OpenDoorRequest"]
        fields = {f.name: f for f in req.fields}
        assert fields["device_id"].number == 1
        assert fields["door_number"].number == 2

    def test_repeated_field(self):
        result = parse_proto(SAMPLE_PROTO)
        msgs = {m.name: m for m in result.messages}
        req = msgs["StreamEventsRequest"]
        fields = {f.name: f for f in req.fields}
        assert fields["event_types"].label == "repeated"

    def test_oneof(self):
        result = parse_proto(SAMPLE_PROTO)
        msgs = {m.name: m for m in result.messages}
        event = msgs["DomophoneEvent"]
        assert len(event.oneofs) == 1
        oneof = event.oneofs[0]
        assert oneof.name == "payload"
        assert len(oneof.fields) == 3

    def test_enum(self):
        result = parse_proto(SAMPLE_PROTO)
        assert len(result.enums) == 1
        enum = result.enums[0]
        assert enum.name == "EventType"
        assert len(enum.values) == 4
        names = [v[0] for v in enum.values]
        assert "EVENT_TYPE_UNSPECIFIED" in names
        assert "EVENT_TYPE_DOOR_OPEN" in names

    def test_inline_comment(self):
        result = parse_proto(SAMPLE_PROTO)
        msgs = {m.name: m for m in result.messages}
        req = msgs["OpenDoorRequest"]
        fields = {f.name: f for f in req.fields}
        assert "Unique device identifier" in fields["device_id"].comment

    def test_preceding_comment(self):
        result = parse_proto(SAMPLE_PROTO)
        svc = result.services[0]
        assert "manages intercom" in svc.comment.lower()


class TestConvertProto:
    def test_returns_markdown_and_metadata(self):
        md, meta = convert_proto(SAMPLE_PROTO, "domophone.proto")
        assert isinstance(md, str)
        assert isinstance(meta, dict)

    def test_title(self):
        md, _ = convert_proto(SAMPLE_PROTO, "domophone.proto")
        assert "# domophone.proto" in md

    def test_package_in_output(self):
        md, _ = convert_proto(SAMPLE_PROTO)
        assert "axxon.domophone.v1" in md

    def test_service_heading(self):
        md, _ = convert_proto(SAMPLE_PROTO)
        assert "## Service `DomophoneService`" in md

    def test_method_signatures(self):
        md, _ = convert_proto(SAMPLE_PROTO)
        assert "rpc OpenDoor" in md
        assert "rpc StreamEvents" in md
        assert "stream DomophoneEvent" in md

    def test_message_heading(self):
        md, _ = convert_proto(SAMPLE_PROTO)
        assert "### Message `OpenDoorRequest`" in md

    def test_field_table(self):
        md, _ = convert_proto(SAMPLE_PROTO)
        assert "| # | Field | Type | Label | Description |" in md
        assert "`device_id`" in md
        assert "`string`" in md

    def test_enum_rendering(self):
        md, _ = convert_proto(SAMPLE_PROTO)
        assert "### Enum `EventType`" in md
        assert "`EVENT_TYPE_DOOR_OPEN`" in md

    def test_oneof_rendering(self):
        md, _ = convert_proto(SAMPLE_PROTO)
        assert "**oneof** `payload`" in md

    def test_metadata_counts(self):
        _, meta = convert_proto(SAMPLE_PROTO)
        assert meta["services"] == 1
        assert meta["methods"] == 3
        assert meta["messages"] >= 7
        assert meta["enums"] == 1
        assert meta["package"] == "axxon.domophone.v1"

    def test_imports_in_output(self):
        md, _ = convert_proto(SAMPLE_PROTO)
        assert "google/protobuf/timestamp.proto" in md


class TestConvertProtoFileOriginalFilename:
    """Test that convert_proto_file uses original_filename for the Markdown title."""

    def test_uses_original_filename_over_temp_path(self):
        """When original_filename is provided, it should appear in the title,
        not the temp file basename."""
        import os
        import tempfile
        from app.ingestion.converters.proto import convert_proto_file

        with tempfile.NamedTemporaryFile(
            suffix=".proto", delete=False, mode="w", encoding="utf-8",
        ) as f:
            f.write(SAMPLE_PROTO)
            f.flush()
            temp_path = f.name

        try:
            md, meta = convert_proto_file(temp_path, original_filename="AcfaService.proto")
            assert "# AcfaService.proto" in md
            assert os.path.basename(temp_path) not in md
        finally:
            os.unlink(temp_path)

    def test_falls_back_to_file_path_basename(self):
        """Without original_filename, should fall back to basename of file_path."""
        import os
        import tempfile
        from app.ingestion.converters.proto import convert_proto_file

        with tempfile.NamedTemporaryFile(
            suffix=".proto", delete=False, mode="w", encoding="utf-8",
        ) as f:
            f.write(SAMPLE_PROTO)
            f.flush()
            temp_path = f.name

        try:
            md, meta = convert_proto_file(temp_path)
            assert f"# {os.path.basename(temp_path)}" in md
        finally:
            os.unlink(temp_path)

    def test_empty_original_filename_uses_path(self):
        """Empty string for original_filename should fall back to file_path basename."""
        import os
        import tempfile
        from app.ingestion.converters.proto import convert_proto_file

        with tempfile.NamedTemporaryFile(
            suffix=".proto", delete=False, mode="w", encoding="utf-8",
        ) as f:
            f.write(SAMPLE_PROTO)
            f.flush()
            temp_path = f.name

        try:
            md, meta = convert_proto_file(temp_path, original_filename="")
            assert f"# {os.path.basename(temp_path)}" in md
        finally:
            os.unlink(temp_path)


ALLMAN_PROTO = """\
syntax = "proto3";

package axxon.acfa;

service AcfaService
{
    rpc ListUnitsActions(ListUnitsActionsRequest) returns (stream ListUnitsActionsResponse);
    rpc ListUnitsEvents(ListUnitsEventsRequest) returns (stream ListUnitsEventsResponse);
}

message ListUnitsActionsRequest
{
    message Unit
    {
        string uid = 1;
    }

    repeated Unit items = 1;
    int32 portion_size = 2;
}

message ListUnitsActionsResponse
{
    repeated string items = 1;
    bool more_data = 2;
}

message ListUnitsEventsRequest
{
    string uid = 1;
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

enum EStatesMode
{
    SM_ALL = 0;
    SM_CURRENT = 1;
}
"""


class TestAllmanStyleBraces:
    """Test parsing of proto files with Allman-style braces (brace on next line)."""

    def test_service_parsed(self):
        result = parse_proto(ALLMAN_PROTO)
        assert len(result.services) == 1
        assert result.services[0].name == "AcfaService"

    def test_service_methods(self):
        result = parse_proto(ALLMAN_PROTO)
        svc = result.services[0]
        assert len(svc.methods) == 2
        names = [m.name for m in svc.methods]
        assert "ListUnitsActions" in names
        assert "ListUnitsEvents" in names

    def test_messages_parsed(self):
        result = parse_proto(ALLMAN_PROTO)
        assert len(result.messages) >= 4
        names = [m.name for m in result.messages]
        assert "ListUnitsActionsRequest" in names
        assert "ListUnitsActionsResponse" in names
        assert "ListUnitsEventsRequest" in names
        assert "ListUnitsEventsResponse" in names

    def test_nested_message_in_allman(self):
        result = parse_proto(ALLMAN_PROTO)
        msgs = {m.name: m for m in result.messages}
        req = msgs["ListUnitsActionsRequest"]
        assert len(req.nested_messages) == 1
        assert req.nested_messages[0].name == "Unit"

    def test_fields_in_allman_message(self):
        result = parse_proto(ALLMAN_PROTO)
        msgs = {m.name: m for m in result.messages}
        resp = msgs["ListUnitsEventsResponse"]
        assert len(resp.fields) == 2
        field_names = [f.name for f in resp.fields]
        assert "items" in field_names
        assert "more_data" in field_names

    def test_enum_parsed_allman(self):
        result = parse_proto(ALLMAN_PROTO)
        assert len(result.enums) == 1
        assert result.enums[0].name == "EStatesMode"
        assert len(result.enums[0].values) == 2

    def test_convert_allman_produces_markdown(self):
        md, meta = convert_proto(ALLMAN_PROTO, "AcfaService.proto")
        assert "# AcfaService.proto" in md
        assert "## Service `AcfaService`" in md
        assert "### Message `ListUnitsEventsResponse`" in md
        assert "### Enum `EStatesMode`" in md
        assert meta["services"] == 1
        assert meta["methods"] == 2
        assert meta["messages"] >= 4
        assert meta["enums"] == 1

    def test_streaming_method_in_allman(self):
        result = parse_proto(ALLMAN_PROTO)
        svc = result.services[0]
        methods = {m.name: m for m in svc.methods}
        assert methods["ListUnitsActions"].server_streaming is True
        assert methods["ListUnitsActions"].client_streaming is False


class TestEdgeCases:
    def test_empty_proto(self):
        md, meta = convert_proto("")
        assert "# Proto Definition" in md
        assert meta["services"] == 0
        assert meta["messages"] == 0

    def test_minimal_message(self):
        proto = 'syntax = "proto3";\nmessage Ping {\n  string id = 1;\n}'
        result = parse_proto(proto)
        assert len(result.messages) == 1
        assert result.messages[0].name == "Ping"

    def test_nested_message(self):
        proto = """\
syntax = "proto3";
message Outer {
  string name = 1;
  message Inner {
    int32 value = 1;
  }
  Inner inner = 2;
}
"""
        result = parse_proto(proto)
        outer = result.messages[0]
        assert outer.name == "Outer"
        assert len(outer.nested_messages) == 1
        assert outer.nested_messages[0].name == "Inner"

    def test_nested_enum(self):
        proto = """\
syntax = "proto3";
message Status {
  enum Code {
    OK = 0;
    ERROR = 1;
  }
  Code code = 1;
}
"""
        result = parse_proto(proto)
        msg = result.messages[0]
        assert len(msg.nested_enums) == 1
        assert msg.nested_enums[0].name == "Code"

    def test_no_filename_uses_default_title(self):
        md, _ = convert_proto('syntax = "proto3";')
        assert "# Proto Definition" in md

    def test_block_comments_skipped(self):
        proto = """\
syntax = "proto3";
/* This is a block comment
   spanning multiple lines */
message Foo {
  string bar = 1;
}
"""
        result = parse_proto(proto)
        assert len(result.messages) == 1
        assert result.messages[0].name == "Foo"

    def test_map_field(self):
        proto = """\
syntax = "proto3";
message Config {
  map<string, string> labels = 1;
}
"""
        result = parse_proto(proto)
        msg = result.messages[0]
        assert len(msg.fields) == 1
        assert "map" in msg.fields[0].label

    def test_optional_field(self):
        proto = """\
syntax = "proto3";
message Req {
  optional string name = 1;
}
"""
        result = parse_proto(proto)
        msg = result.messages[0]
        assert msg.fields[0].label == "optional"


# ---------------------------------------------------------------------------
# Regression: real AcfaService.proto-like content
# ---------------------------------------------------------------------------

ACFA_LIKE_PROTO = """\
syntax = "proto3";
package axxonsoft.bl.acfa;
option go_package = "bitbucket.org/Axxonsoft/bl/acfa";

import "google/protobuf/wrappers.proto";
import "google/rpc/status.proto";

message RangeConstraint
{
    oneof min {
        int32 min_int = 1;
        double min_double = 2;
    };
    oneof max {
        int32 max_int = 10;
        double max_double = 11;
    };
}

message PropertyDescriptor
{
    string id = 1;
    string name = 2;
    string type = 3;
    bool readonly = 4;

    oneof value {
        string value_string = 20;
        int32 value_int32 = 21;
    }
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

message Event
{
    string id = 1;
    string name = 2;
    repeated PropertyDescriptor params = 4;
}

message ListUnitsEventsResponse
{
    message UnitEvents
    {
        string uid = 1;
        repeated Event events = 2;
    }

    repeated UnitEvents items = 1;
    bool more_data = 2;
}

message ListUnitsStatesRequest
{
    enum EStatesMode
    {
        SM_ALL = 0;
        SM_CURRENT = 1;
    }

    message Unit
    {
        string uid = 1;
        EStatesMode mode = 2;
    }

    repeated Unit items = 1;
    int32 portion_size = 2;
}

service AcfaService
{
    rpc ListUnitsEvents(ListUnitsEventsRequest) returns (stream ListUnitsEventsResponse);
    rpc PerformAction(PerformActionRequest) returns (PerformActionResponse);
}
"""


class TestAcfaLikeProto:
    """Regression tests modeled after the real AcfaService.proto structure."""

    def test_all_messages_parsed(self):
        result = parse_proto(ACFA_LIKE_PROTO)
        names = [m.name for m in result.messages]
        assert "RangeConstraint" in names
        assert "PropertyDescriptor" in names
        assert "ListUnitsEventsRequest" in names
        assert "Event" in names
        assert "ListUnitsEventsResponse" in names
        assert "ListUnitsStatesRequest" in names

    def test_service_parsed(self):
        result = parse_proto(ACFA_LIKE_PROTO)
        assert len(result.services) == 1
        assert result.services[0].name == "AcfaService"
        assert len(result.services[0].methods) == 2

    def test_nested_message_unit(self):
        result = parse_proto(ACFA_LIKE_PROTO)
        msgs = {m.name: m for m in result.messages}
        req = msgs["ListUnitsEventsRequest"]
        assert len(req.nested_messages) == 1
        assert req.nested_messages[0].name == "Unit"
        assert len(req.nested_messages[0].fields) == 1

    def test_nested_enum_in_message(self):
        result = parse_proto(ACFA_LIKE_PROTO)
        msgs = {m.name: m for m in result.messages}
        states_req = msgs["ListUnitsStatesRequest"]
        assert len(states_req.nested_enums) == 1
        assert states_req.nested_enums[0].name == "EStatesMode"
        assert len(states_req.nested_enums[0].values) == 2

    def test_deeply_nested_allman(self):
        """Message with both nested enum and nested message, all Allman-style."""
        result = parse_proto(ACFA_LIKE_PROTO)
        msgs = {m.name: m for m in result.messages}
        states_req = msgs["ListUnitsStatesRequest"]
        assert len(states_req.nested_messages) == 1
        assert states_req.nested_messages[0].name == "Unit"
        unit_fields = {f.name: f for f in states_req.nested_messages[0].fields}
        assert "uid" in unit_fields
        assert "mode" in unit_fields

    def test_oneof_in_allman_message(self):
        result = parse_proto(ACFA_LIKE_PROTO)
        msgs = {m.name: m for m in result.messages}
        rc = msgs["RangeConstraint"]
        assert len(rc.oneofs) >= 2
        oneof_names = [o.name for o in rc.oneofs]
        assert "min" in oneof_names
        assert "max" in oneof_names

    def test_response_fields(self):
        result = parse_proto(ACFA_LIKE_PROTO)
        msgs = {m.name: m for m in result.messages}
        resp = msgs["ListUnitsEventsResponse"]
        field_names = [f.name for f in resp.fields]
        assert "items" in field_names
        assert "more_data" in field_names

    def test_nested_response_message(self):
        result = parse_proto(ACFA_LIKE_PROTO)
        msgs = {m.name: m for m in result.messages}
        resp = msgs["ListUnitsEventsResponse"]
        assert len(resp.nested_messages) == 1
        assert resp.nested_messages[0].name == "UnitEvents"

    def test_streaming_rpc(self):
        result = parse_proto(ACFA_LIKE_PROTO)
        svc = result.services[0]
        methods = {m.name: m for m in svc.methods}
        assert methods["ListUnitsEvents"].server_streaming is True
        assert methods["ListUnitsEvents"].client_streaming is False

    def test_markdown_contains_all_key_elements(self):
        md, meta = convert_proto(ACFA_LIKE_PROTO, "AcfaService.proto")
        assert "# AcfaService.proto" in md
        assert "## Service `AcfaService`" in md
        assert "### Message `ListUnitsEventsResponse`" in md
        assert "### Message `PropertyDescriptor`" in md
        assert "`ListUnitsEventsRequest`" in md
        assert "rpc ListUnitsEvents" in md
        assert meta["services"] == 1
        assert meta["messages"] >= 6

    def test_markdown_has_field_tables(self):
        md, _ = convert_proto(ACFA_LIKE_PROTO, "AcfaService.proto")
        assert "`id`" in md
        assert "`name`" in md
        assert "`readonly`" in md
        assert "`items`" in md
        assert "`more_data`" in md


# ---------------------------------------------------------------------------
# convert_proto_file with Allman + original_filename
# ---------------------------------------------------------------------------

class TestConvertProtoFileAllmanWithFilename:
    """Verify convert_proto_file handles Allman-style AND original_filename together."""

    def test_allman_file_with_original_filename(self):
        import os
        import tempfile
        from app.ingestion.converters.proto import convert_proto_file

        with tempfile.NamedTemporaryFile(
            suffix=".proto", delete=False, mode="w", encoding="utf-8",
        ) as f:
            f.write(ACFA_LIKE_PROTO)
            f.flush()
            temp_path = f.name

        try:
            md, meta = convert_proto_file(temp_path, original_filename="AcfaService.proto")
            assert "# AcfaService.proto" in md
            assert os.path.basename(temp_path) not in md
            assert "## Service `AcfaService`" in md
            assert "### Message `ListUnitsEventsResponse`" in md
            assert meta["services"] == 1
            assert meta["messages"] >= 6
        finally:
            os.unlink(temp_path)

    def test_allman_file_without_original_filename(self):
        import os
        import tempfile
        from app.ingestion.converters.proto import convert_proto_file

        with tempfile.NamedTemporaryFile(
            suffix=".proto", delete=False, mode="w", encoding="utf-8",
        ) as f:
            f.write(ACFA_LIKE_PROTO)
            f.flush()
            temp_path = f.name

        try:
            md, meta = convert_proto_file(temp_path)
            assert f"# {os.path.basename(temp_path)}" in md
            assert meta["services"] == 1
            assert meta["messages"] >= 6
        finally:
            os.unlink(temp_path)


# ---------------------------------------------------------------------------
# New capabilities enabled by proto-schema-parser
# ---------------------------------------------------------------------------

class TestReservedFields:
    """Test that reserved declarations don't break parsing."""

    def test_reserved_numbers(self):
        proto = """\
syntax = "proto3";
message Msg {
  reserved 2, 15, 9 to 11;
  string name = 1;
}
"""
        result = parse_proto(proto)
        assert len(result.messages) == 1
        assert result.messages[0].fields[0].name == "name"

    def test_reserved_names(self):
        proto = """\
syntax = "proto3";
message Msg {
  reserved "foo", "bar";
  string name = 1;
}
"""
        result = parse_proto(proto)
        assert len(result.messages) == 1
        assert result.messages[0].fields[0].name == "name"


class TestFieldOptions:
    """Test fields with options like [packed=true]."""

    def test_packed_option(self):
        proto = """\
syntax = "proto3";
message Msg {
  repeated int32 values = 1 [packed=true];
}
"""
        result = parse_proto(proto)
        msg = result.messages[0]
        assert msg.fields[0].name == "values"
        assert msg.fields[0].label == "repeated"

    def test_deprecated_option(self):
        proto = """\
syntax = "proto3";
message Msg {
  string old_field = 1 [deprecated=true];
  string new_field = 2;
}
"""
        result = parse_proto(proto)
        msg = result.messages[0]
        assert len(msg.fields) == 2
        assert msg.fields[0].name == "old_field"
        assert msg.fields[1].name == "new_field"


class TestProto2Syntax:
    """Test proto2 files are handled correctly."""

    def test_proto2_required_field(self):
        proto = """\
syntax = "proto2";
message Msg {
  required string name = 1;
  optional int32 age = 2;
}
"""
        result = parse_proto(proto)
        assert result.syntax == "proto2"
        msg = result.messages[0]
        assert len(msg.fields) == 2
        fields = {f.name: f for f in msg.fields}
        assert fields["name"].label == "required"
        assert fields["age"].label == "optional"

    def test_proto2_service(self):
        proto = """\
syntax = "proto2";
service LegacyService {
  rpc GetData(GetDataRequest) returns (GetDataResponse);
}
message GetDataRequest {
  required string id = 1;
}
message GetDataResponse {
  optional string data = 1;
}
"""
        result = parse_proto(proto)
        assert len(result.services) == 1
        assert result.services[0].name == "LegacyService"
        assert len(result.messages) == 2


class TestComplexComments:
    """Test various comment styles are preserved."""

    def test_multiline_block_comment_on_service(self):
        proto = """\
syntax = "proto3";
/* This service handles
   all authentication
   operations. */
service AuthService {
  rpc Login(LoginRequest) returns (LoginResponse);
}
message LoginRequest { string user = 1; }
message LoginResponse { string token = 1; }
"""
        result = parse_proto(proto)
        svc = result.services[0]
        assert "authentication" in svc.comment.lower()

    def test_inline_comment_on_field(self):
        proto = """\
syntax = "proto3";
message Cfg {
  string host = 1; // Server hostname
  int32 port = 2;  // Server port
}
"""
        result = parse_proto(proto)
        fields = {f.name: f for f in result.messages[0].fields}
        assert "hostname" in fields["host"].comment.lower()
        assert "port" in fields["port"].comment.lower()


class TestMinifiedProto:
    """Test that minified (single-line) proto is parsed correctly."""

    def test_minified_message(self):
        proto = 'syntax="proto3";message M{string a=1;int32 b=2;}'
        result = parse_proto(proto)
        assert len(result.messages) == 1
        assert result.messages[0].name == "M"
        assert len(result.messages[0].fields) == 2

    def test_minified_service(self):
        proto = 'syntax="proto3";service S{rpc Do(Req) returns (Resp);}message Req{string id=1;}message Resp{bool ok=1;}'
        result = parse_proto(proto)
        assert len(result.services) == 1
        assert result.services[0].methods[0].name == "Do"
        assert len(result.messages) == 2


class TestRpcWithBody:
    """Test RPC methods with option bodies."""

    def test_rpc_with_options_block(self):
        proto = """\
syntax = "proto3";
import "google/api/annotations.proto";
service Api {
  rpc GetItem(GetItemRequest) returns (Item) {
    option (google.api.http) = {
      get: "/v1/items/{id}"
    };
  }
}
message GetItemRequest { string id = 1; }
message Item { string name = 1; }
"""
        result = parse_proto(proto)
        assert len(result.services) == 1
        svc = result.services[0]
        assert len(svc.methods) == 1
        assert svc.methods[0].name == "GetItem"
