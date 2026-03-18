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
