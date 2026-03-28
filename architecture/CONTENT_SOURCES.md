# Lexiro — Content Sources: Verified Import URLs

> **Status**: v1.0 — March 28, 2026
> **Author**: Oleg Voitekhovich
> **Purpose**: Operational reference of verified URLs for content ingestion into Lexiro. All links checked and confirmed working.
>
> Related: [CONTENT_PLAN.md](CONTENT_PLAN.md) · [FLOWS.md](FLOWS.md) · [PARTNERSHIP_MARKETING.md](PARTNERSHIP_MARKETING.md)

---

## How to Use This File

Each section lists verified URLs grouped by vendor/standard. The **Method** column indicates which Lexiro ingestion pipeline to use:

| Method | Description |
|--------|-------------|
| `confluence` | Confluence space crawler (`converters/confluence.py`) |
| `web` | Web page scraper (`converters/web.py`) |
| `pdf` | PDF upload (PyMuPDF + OCR) |
| `swagger` | OpenAPI/Swagger spec import |
| `markdown` | Direct Markdown import |
| `proto` | Protobuf file import |
| `archive` | ZIP/7z/tar batch upload |

---

## Tier A — Founding Partners & Market Leaders

### 1. AxxonSoft (Confluence)

| Resource | URL | Method | Status |
|----------|-----|:------:|:------:|
| Documentation Portal (root) | `https://docs.axxonsoft.com` | `confluence` | OK |
| Server HTTP API (Axxon One 2.0) | `https://docs.axxonsoft.com/confluence/spaces/one20en/pages/246486979/Server+HTTP+API` | `confluence` | OK |
| Integration APIs (Axxon One 2.0) | `https://docs.axxonsoft.com/confluence/spaces/one20en/pages/246486976/Integration+APIs` | `confluence` | OK |
| Documentation Root (Axxon One 2.0 EN) | `https://docs.axxonsoft.com/confluence/spaces/one20en/pages/246484043/Documentation` | `confluence` | OK |

**Note**: Old-style URLs (`/display/next1/...`) are deprecated. Use the `/confluence/spaces/one20en/...` format.

**Ingestion strategy**: Use Confluence crawler to import entire `one20en` space for full Axxon One 2.0 coverage.

---

### 2. Axis Communications — VAPIX

URL pattern: `https://developer.axis.com/vapix/network-video/{api-name}/`

#### Root Pages

| Resource | URL | Method | Status |
|----------|-----|:------:|:------:|
| Developer Portal (main) | `https://developer.axis.com` | `web` | OK |
| VAPIX Library (root) | `https://developer.axis.com/vapix/` | `web` | OK |
| Network Video APIs (index) | `https://developer.axis.com/vapix/network-video` | `web` | OK |
| All APIs (catalog) | `https://developer.axis.com/api` | `web` | OK |
| ACAP SDK (edge apps) | `https://developer.axis.com/acap` | `web` | OK |

#### VAPIX Network Video — Individual APIs

| API | URL | Method |
|-----|-----|:------:|
| PTZ Control | `https://developer.axis.com/vapix/network-video/pantiltzoom-api/` | `web` |
| Video Streaming | `https://developer.axis.com/vapix/network-video/video-streaming/` | `web` |
| Event & Action Services | `https://developer.axis.com/vapix/network-video/event-and-action-services/` | `web` |
| Imaging API | `https://developer.axis.com/vapix/network-video/imaging-api/` | `web` |
| Overlay API | `https://developer.axis.com/vapix/network-video/overlay-api/` | `web` |
| Edge Storage API | `https://developer.axis.com/vapix/network-video/edge-storage-api/` | `web` |
| Parameter Management | `https://developer.axis.com/vapix/network-video/parameter-management/` | `web` |
| System Settings | `https://developer.axis.com/vapix/network-video/system-settings/` | `web` |
| Network Settings API | `https://developer.axis.com/vapix/network-video/network-settings-api/` | `web` |
| Basic Device Information | `https://developer.axis.com/vapix/network-video/basic-device-information/` | `web` |
| API Discovery Service | `https://developer.axis.com/vapix/network-video/api-discovery-service/` | `web` |
| Input and Outputs (I/O) | `https://developer.axis.com/vapix/network-video/input-and-outputs/` | `web` |
| Media Stream over HTTP | `https://developer.axis.com/vapix/network-video/media-stream-over-http/` | `web` |
| Rate Control | `https://developer.axis.com/vapix/network-video/rate-control/` | `web` |
| Zipstream Technology | `https://developer.axis.com/vapix/network-video/zipstream-technology/` | `web` |
| MQTT Client API | `https://developer.axis.com/vapix/network-video/mqtt-client-api/` | `web` |
| MQTT Event Bridge | `https://developer.axis.com/vapix/network-video/mqtt-event-bridge/` | `web` |
| Light Control | `https://developer.axis.com/vapix/network-video/light-control/` | `web` |
| Guard Tour API | `https://developer.axis.com/vapix/network-video/guard-tour-api/` | `web` |
| Capture Mode | `https://developer.axis.com/vapix/network-video/capture-mode/` | `web` |
| Firmware Management | `https://developer.axis.com/vapix/network-video/firmware-management-api/` | `web` |
| Serial Port API | `https://developer.axis.com/vapix/network-video/serial-port-api/` | `web` |
| PTZ Autotracker API | `https://developer.axis.com/vapix/network-video/ptz-autotracker-api/` | `web` |
| Thermal Imaging | `https://developer.axis.com/vapix/network-video/thermal-imaging/` | `web` |
| Thermometry | `https://developer.axis.com/vapix/network-video/thermometry/` | `web` |
| Event Streaming over WebSocket | `https://developer.axis.com/vapix/network-video/event-streaming-over-websocket/` | `web` |
| Certificate Management | `https://developer.axis.com/vapix/network-video/certificate-management-api/` | `web` |
| Signed Video | `https://developer.axis.com/vapix/network-video/signed-video/` | `web` |
| Optics Control | `https://developer.axis.com/vapix/network-video/optics-control/` | `web` |
| DayNight API | `https://developer.axis.com/vapix/network-video/daynight-api/` | `web` |
| Siren and Light | `https://developer.axis.com/vapix/network-video/siren-and-light/` | `web` |
| Decoder API | `https://developer.axis.com/vapix/network-video/decoder-api/` | `web` |
| Geolocation API | `https://developer.axis.com/vapix/network-video/geolocation-api/` | `web` |
| Stream Profiles | `https://developer.axis.com/vapix/network-video/stream-profiles/` | `web` |
| View Area API | `https://developer.axis.com/vapix/network-video/view-area-api/` | `web` |
| On-screen Controls | `https://developer.axis.com/vapix/network-video/on-screen-controls/` | `web` |
| RTSP Adjustable Live Stream | `https://developer.axis.com/vapix/network-video/rtsp-adjustable-live-stream/` | `web` |
| Remote Syslog | `https://developer.axis.com/vapix/network-video/remote-syslog/` | `web` |
| Analytics Metadata Producer | `https://developer.axis.com/vapix/network-video/analytics-metadata-producer-configuration/` | `web` |
| Time API | `https://developer.axis.com/vapix/network-video/time-api/` | `web` |
| Systemready API | `https://developer.axis.com/vapix/network-video/systemready-api/` | `web` |
| Power Settings | `https://developer.axis.com/vapix/network-video/power-settings/` | `web` |
| RAID Management | `https://developer.axis.com/vapix/network-video/raid-management/` | `web` |

#### Axis GitHub Repositories

| Repository | URL | Description |
|------------|-----|-------------|
| AxisCommunications (org) | `https://github.com/AxisCommunications` | 52 repos, 424 followers |
| ACAP Native SDK Examples | `https://github.com/AxisCommunications/acap-native-sdk-examples` | Edge app development examples |
| Media Stream Library JS | `https://github.com/AxisCommunications/media-stream-library-js` | JavaScript RTSP/H.264 streaming |

**Ingestion strategy**: Crawl `https://developer.axis.com/vapix/network-video` and all subpages. ~40 API pages → estimated 400–600 chunks.

---

### 3. Hikvision

| Resource | URL | Method | Status | Notes |
|----------|-----|:------:|:------:|-------|
| Open Platform (China) | `https://open.hikvision.com` | — | OK | Chinese-language portal |
| TPP Portal (ISAPI downloads) | `https://tpp.hikvision.com/download/ISAPI_OTAP` | `pdf` | Requires registration | Technical Partner Portal |
| TPP Open Capabilities | `https://tpp.hikvision.com/tpp/OpenCapabilities` | `pdf` | Requires registration | Full API capabilities catalog |
| Unofficial ISAPI Specs (GitHub) | `https://github.com/sakharin/hikvision-apis` | `markdown` | OK | Community-maintained, useful as supplement |

**Note**: `open.hikvision.com` English sub-pages (`/en/equipment-docking.html`, `/en/platform-docking.html`) return 404. The portal is China-focused. Use the TPP portal for English ISAPI documentation.

**Ingestion strategy**: Download ISAPI PDF from TPP portal → PDF upload. Supplement with GitHub community specs.

---

### 4. Dahua

| Resource | URL | Method | Status | Notes |
|----------|-----|:------:|:------:|-------|
| Open Platform | `https://open.dahuatech.com` | — | Requires registration | Developer portal |

**Ingestion strategy**: Register as developer/integrator → download HTTP API PDFs → PDF upload.

---

### 5. Genetec

| Resource | URL | Method | Status | Notes |
|----------|-----|:------:|:------:|-------|
| Developer Portal | `https://developer.genetec.com` | `swagger` / `web` | Requires registration (free) | Web SDK REST API + Swagger specs |

**Ingestion strategy**: Swagger import for REST API + web scraper for documentation pages.

---

### 6. Grundig Security

Access via AxxonSoft partnership contact. Documentation provided as PDF files.

**Ingestion strategy**: PDF upload (PyMuPDF + OCR for scanned pages).

---

### 7. HID Global

Access partially public, full SDK docs require partner program registration.

**Ingestion strategy**: PDF upload for publicly available specs.

---

## Tier C — Standards & Protocols

### ONVIF

| Resource | URL | Method | Status |
|----------|-----|:------:|:------:|
| Profiles Overview | `https://www.onvif.org/profiles/` | `web` | OK |
| Profile S (Video Streaming) | `https://www.onvif.org/profiles/profile-s/` | `web` | OK |
| Profile T (Advanced Video) | `https://www.onvif.org/profiles/profile-t/` | `web` | OK |
| Profile G (Edge Storage) | `https://www.onvif.org/profiles/profile-g/` | `web` | OK |
| Profile M (Metadata/Analytics) | `https://www.onvif.org/profiles/profile-m/` | `web` | OK |
| Profile A (Access Control) | `https://www.onvif.org/profiles/profile-a/` | `web` | OK |
| Profile C (Door/Credential) | `https://www.onvif.org/profiles/profile-c/` | `web` | OK |
| Profile D (Peripheral Devices) | `https://www.onvif.org/profiles/profile-d/` | `web` | OK |
| Specifications Index | `https://www.onvif.org/specs/` | `pdf` | OK (slow) |
| GitHub — WSDL + Specs | `https://github.com/onvif/specs` | `markdown` / `proto` | OK (414 stars) |

**Note**: Direct PDF links (e.g., `/specs/core/ONVIF-Core-Spec.pdf`) do not work. Download specs via the specs index page or from GitHub.

**Ingestion strategy**: Web scrape profile pages + download PDFs from GitHub `onvif/specs` repo.

---

### IETF RFCs

| Standard | RFC | URL | Method | Status |
|----------|-----|-----|:------:|:------:|
| RTSP 2.0 | RFC 7826 | `https://www.rfc-editor.org/rfc/rfc7826` | `web` | OK |
| RTSP 1.0 | RFC 2326 | `https://www.rfc-editor.org/rfc/rfc2326` | `web` | OK |
| RTP/RTCP | RFC 3550 | `https://www.rfc-editor.org/rfc/rfc3550` | `web` | OK |
| SDP | RFC 8866 | `https://www.rfc-editor.org/rfc/rfc8866` | `web` | OK |
| SIP | RFC 3261 | `https://www.rfc-editor.org/rfc/rfc3261` | `web` | OK |
| CoAP | RFC 7252 | `https://www.rfc-editor.org/rfc/rfc7252` | `web` | OK |
| DTMF (RTP Events) | RFC 4733 | `https://www.rfc-editor.org/rfc/rfc4733` | `web` | OK |

**Ingestion strategy**: Web import — RFC pages are clean text, excellent for chunking.

---

### OpenAPI

| Resource | URL | Method | Status |
|----------|-----|:------:|:------:|
| OpenAPI 3.1.0 Specification | `https://spec.openapis.org/oas/v3.1.0` | `web` | OK |
| GitHub — OpenAPI Specification | `https://github.com/OAI/OpenAPI-Specification` | `markdown` | OK (31K stars) |

---

## Quick Start: First 5 Imports

Recommended order for initial content population (Week 1):

| # | Source | URL | Method | Est. Chunks |
|:-:|--------|-----|:------:|:-----------:|
| 1 | Axis VAPIX (all APIs) | `https://developer.axis.com/vapix/network-video` | `web` (crawl subpages) | 400–600 |
| 2 | AxxonSoft Confluence | `https://docs.axxonsoft.com` (space: `one20en`) | `confluence` | 300–500 |
| 3 | ONVIF Profiles + Specs | `https://www.onvif.org/profiles/` + `https://github.com/onvif/specs` | `web` + `markdown` | 200–400 |
| 4 | RTSP RFC 7826 | `https://www.rfc-editor.org/rfc/rfc7826` | `web` | 50–100 |
| 5 | OpenAPI 3.1 Spec | `https://spec.openapis.org/oas/v3.1.0` | `web` | 50–100 |

**Total estimated first-batch**: ~1,000–1,700 chunks — enough for a meaningful developer experience.

---

## Link Verification Log

All URLs in this document were manually verified on **March 28, 2026**.

| Category | Total Links | OK | Requires Registration | Notes |
|----------|:-----------:|:--:|:---------------------:|-------|
| AxxonSoft | 4 | 4 | 0 | Old `/display/next1/` URLs deprecated |
| Axis VAPIX | 44 | 44 | 0 | Pattern: `/vapix/network-video/{api-name}/` |
| Hikvision | 4 | 2 | 2 | TPP portal requires partner registration |
| ONVIF | 10 | 10 | 0 | Direct PDF links broken; use specs index |
| IETF RFCs | 7 | 7 | 0 | All public, stable URLs |
| OpenAPI | 2 | 2 | 0 | |
| **Total** | **71** | **69** | **2** | |
