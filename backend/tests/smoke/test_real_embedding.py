"""Smoke test: real embedding model + real pgvector = quality search results.

This test uses the actual multilingual-e5-large model (no mocks).
First run downloads the model (~1.1GB) and takes ~60 seconds.
Subsequent runs use the cached model and take ~10 seconds.
"""

import pytest

from app.ingestion.pipeline import ingest_file
from app.search.service import search_documents

pytestmark = pytest.mark.smoke

SMOKE_MD_CONTENT = """# Smart Access Controller Documentation

## Door Control API

### Opening Doors Remotely
To open a door remotely via the API, send a POST request to /doors/{id}/open.
The request must include the authentication token and door ID.
The door will unlock for the configured duration (default 5 seconds).
Response includes the door status and timestamp.

### Locking Doors
To lock a door, send a POST request to /doors/{id}/lock.
This immediately engages the electronic lock mechanism.
The door sensor will confirm the locked state.

## Camera Integration

### Live Video Streaming
To start a live video stream, call GET /cameras/{id}/stream.
The response includes an RTSP URL for the camera feed.
Supported protocols: RTSP, HLS, WebSocket.
Resolution can be configured via query parameters.

### Recording Playback
To play back recorded video, use GET /cameras/{id}/playback.
Specify start_time and end_time in ISO 8601 format.
The API returns a temporary streaming URL valid for 1 hour.

## User Management

### Creating Users
To create a new user, send POST /users with name, role, and credentials.
Supported roles: admin, operator, viewer.
Each user can be assigned to specific doors and cameras.

### Access Permissions
Permissions are managed via access groups.
Each group defines which doors and time zones a user can access.
Use PUT /users/{id}/permissions to update access rights.

## Event Monitoring

### Real-time Event Stream
Subscribe to events via WebSocket at /events/stream.
Events include door access, alarms, and system notifications.
Each event has a type, timestamp, source device, and description.

### Event History Search
Search historical events via GET /events with filters.
Supported filters: event_type, device_id, start_date, end_date.
Results are paginated with configurable page size.
"""


@pytest.fixture
def smoke_md_file(tmp_path):
    path = tmp_path / "smoke_test_doc.md"
    path.write_text(SMOKE_MD_CONTENT, encoding="utf-8")
    return str(path)


class TestRealEmbeddingSearch:
    async def test_door_query_finds_door_content(self, db_session_smoke, smoke_md_file):
        """'how to open door remotely' should find the door control section."""
        await ingest_file(
            session=db_session_smoke,
            file_path=smoke_md_file,
            product_name="SmartController",
            firmware_version="1.0",
        )

        results = await search_documents(
            db_session_smoke,
            "how to open door remotely",
            limit=3,
        )

        assert len(results) > 0
        top_result = results[0]
        content_lower = top_result["content"].lower()
        assert any(
            keyword in content_lower
            for keyword in ["door", "open", "unlock", "lock"]
        ), f"Top result should be about doors, got: {top_result['heading_path']}"

    async def test_camera_query_finds_camera_content(self, db_session_smoke, smoke_md_file):
        """'video streaming from camera' should find the camera section."""
        await ingest_file(
            session=db_session_smoke,
            file_path=smoke_md_file,
            product_name="SmartController",
            firmware_version="1.0",
        )

        results = await search_documents(
            db_session_smoke,
            "video streaming from camera",
            limit=3,
        )

        assert len(results) > 0
        top_result = results[0]
        content_lower = top_result["content"].lower()
        assert any(
            keyword in content_lower
            for keyword in ["camera", "stream", "video", "rtsp"]
        ), f"Top result should be about cameras, got: {top_result['heading_path']}"
