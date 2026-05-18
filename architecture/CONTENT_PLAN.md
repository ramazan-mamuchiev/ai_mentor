# AI Mentor — Content Plan: Documentation Sources & Ingestion Priorities

> **Status**: v1.0 — March 28, 2026
> **Author**: Oleg Voitekhovich
> **Purpose**: Structured plan for populating the AI Mentor knowledge base with vendor documentation, protocol specs, and industry standards
>
> Related: [CONTENT_SOURCES.md](CONTENT_SOURCES.md) · [PARTNERSHIP_MARKETING.md](PARTNERSHIP_MARKETING.md) · [GTM_STRATEGY.md](GTM_STRATEGY.md) · [FLOWS.md](FLOWS.md) · [MARKET_RESEARCH.md](MARKET_RESEARCH.md)

---

## 1. Ingestion Capabilities (Current)

AI Mentor supports 8 document formats — each with a dedicated converter in the ingestion pipeline:

| Format | Extensions | Converter | Ingestion Method |
|--------|-----------|-----------|-----------------|
| Markdown | `.md` | Direct H1–H6 chunking | Upload / Archive |
| Swagger / OpenAPI 2.0/3.x | `.json`, `.yaml` | 1 chunk per endpoint (structured) | Upload / Archive |
| Postman Collection v2.1 | `.json` | Request → endpoint docs conversion | Upload / Archive |
| PDF (text-based) | `.pdf` | PyMuPDF → parallel chunking | Upload / TUS |
| PDF (scanned / OCR) | `.pdf` | PyMuPDF + Gemini Vision OCR | Upload / TUS |
| Web page | URL | httpx + BeautifulSoup → cleanup | URL import |
| Protobuf | `.proto` | Service/method/message extraction | Upload / Archive |
| Confluence | Space URL | Space crawl → parallel page ingestion | URL import |

Archive formats (ZIP, 7z, tar, tar.gz, tar.bz2, tar.xz, RAR) allow batch upload of multiple files in one operation.

Full pipeline details: [FLOWS.md — Ingestion Pipeline](FLOWS.md#ingestion-pipeline-async-via-celery-multi-format)

---

## 2. Content Tiers & Priorities

Content sources are organized into 4 tiers aligned with the GTM strategy (see [GTM_STRATEGY.md](GTM_STRATEGY.md)):

| Tier | Description | Timeline | Target Volume |
|:----:|-------------|:--------:|:-------------:|
| **A** | Founding partners + market leaders | Week 1–4 | 5–7 vendors |
| **B** | High-value niche vendors | Month 2–3 | 7–10 vendors |
| **C** | Protocols & standards (cross-vendor) | Month 1–3 | 15–20 specs |
| **D** | Long-tail vendors (catalog mass) | Month 3–6 | 50–100 vendors |

---

## 3. Tier A — Founding Partners & Market Leaders

Priority vendors with the largest partner networks and immediate GTM value.

### 3.1 AxxonSoft (VMS / PSIM) — Founding Strategic Partner

> See [PARTNERSHIP_MARKETING.md — Section 3](PARTNERSHIP_MARKETING.md#3-founding-strategic-partner-axxonsoft) for full partnership plan.

| Source | Format | Location | Priority |
|--------|--------|----------|:--------:|
| Axxon One HTTP API | Confluence | `docs.axxonsoft.com` → Axxon One Developer → HTTP API | **P0** |
| Axxon One gRPC API | Protobuf (`.proto`) + Confluence | gRPC service definitions + Confluence docs | **P0** |
| Axxon One WebSocket API | Confluence / Web | Real-time event streams, notifications | **P1** |
| Axxon PSIM (Intellect) IIDK | PDF / Confluence | Integration Development Kit — COM/ActiveX interface | **P1** |
| Axxon PSIM HTTP Server API | Swagger / Confluence | REST API for Axxon Intellect platform | **P1** |
| Axxon One SDK Examples | Markdown / Code archives | Python, C#, JavaScript integration samples | **P2** |
| AxxonSoft Device Integration Pack | Confluence | 10,000+ supported device models, driver parameters | **P2** |

**Ingestion method**: Confluence space crawler (`converters/confluence.py`) — automated full-space import.

**Estimated volume**: ~500–1,000 chunks across all sources.

---

### 3.2 Grundig Security (Cameras) — Founding Hardware Partner

> See [PARTNERSHIP_MARKETING.md — Section 3b](PARTNERSHIP_MARKETING.md#3b-founding-strategic-partner-grundig-security) for full partnership plan.

| Source | Format | Description | Priority |
|--------|--------|------------|:--------:|
| Grundig SMART Line Camera API | PDF | Edge AI analytics: LPR, face recognition, people counting, crowd analysis, audio analysis, queue management | **P0** |
| Grundig ISAPI / HTTP API | PDF / Swagger | HTTP commands for camera control, configuration, streaming | **P0** |
| Grundig Integration Guides | PDF | VMS integration guides (Axxon One, Milestone, Genetec) | **P1** |
| Grundig Camera Configuration | PDF | Device setup, network config, video parameters | **P2** |
| Grundig + Axxon One Integration | PDF / Web | Joint documentation: SMART cameras with Axxon One Quick Smart Search | **P1** |

**Ingestion method**: PDF upload (PyMuPDF + OCR for scanned pages).

**Access**: via AxxonSoft partnership contact (Grundig is an AxxonSoft Solution Partner).

**Estimated volume**: ~200–400 chunks.

---

### 3.3 Hikvision

| Source | Format | Location | Priority |
|--------|--------|----------|:--------:|
| ISAPI (IP Surveillance API) | PDF (200+ pages) | `open.hikvision.com` — core HTTP API for all Hikvision devices | **P0** |
| HikCentral Professional Open API | Swagger / PDF | `open.hikvision.com` — VMS platform REST API | **P1** |
| HikCentral Enterprise API | Swagger / PDF | Enterprise platform API (access control, video, events) | **P1** |
| iVMS SDK | PDF / Archive (ZIP) | Desktop/mobile client SDK | **P2** |
| SADP Protocol | PDF | Automatic device discovery protocol | **P2** |
| Hikvision Embedded SDK (Device Network SDK) | PDF | Low-level device control SDK | **P2** |
| Hikvision ONVIF Implementation Notes | PDF | Vendor-specific ONVIF extensions and limitations | **P2** |

**Ingestion method**: PDF upload. Some Swagger specs may be available as JSON/YAML.

**Access**: `open.hikvision.com` — requires free developer account registration.

**Estimated volume**: ~800–1,500 chunks (ISAPI alone is 200+ pages).

---

### 3.4 Dahua

| Source | Format | Location | Priority |
|--------|--------|----------|:--------:|
| Dahua HTTP API (CGI Commands) | PDF | HTTP CGI interface for cameras, NVR, DVR | **P0** |
| Dahua Open Platform API | Swagger / PDF | `open.dahuatech.com` — REST API | **P1** |
| DSS (Dahua Security Software) API | PDF | VMS platform API | **P1** |
| Dahua DHOP SDK | PDF / Archive | Open Platform for edge applications on Dahua devices | **P2** |
| Dahua Smart Plan SDK | PDF | AI analytics configuration API | **P2** |

**Ingestion method**: PDF upload + Swagger import where available.

**Access**: `open.dahuatech.com` — developer registration. Many PDFs downloadable from partner portal.

**Estimated volume**: ~500–800 chunks.

---

### 3.5 Axis Communications

| Source | Format | Location | Priority |
|--------|--------|----------|:--------:|
| VAPIX API (HTTP API) | Web / PDF | `developer.axis.com/vapix` — full HTTP API for all Axis devices | **P0** |
| VAPIX Library — PTZ Control | Web | Pan/Tilt/Zoom commands, presets, guard tours | **P0** |
| VAPIX Library — Video Streaming | Web | RTSP, MJPEG, H.264/H.265 streaming parameters | **P0** |
| VAPIX Library — Event System | Web | Action rules, event triggers, notifications | **P1** |
| VAPIX Library — Analytics API | Web | Object Analytics, ACAP analytics integration | **P1** |
| ACAP SDK (Application Platform) | Web / Markdown | `developer.axis.com/acap` — edge app development | **P1** |
| AXIS Camera Station API | PDF / Swagger | VMS platform API | **P2** |
| AXIS Body Worn Camera API | Web | Body camera integration API | **P2** |

**Ingestion method**: Web scraper (`converters/web.py`) for developer.axis.com pages. PDF for downloadable specs.

**Access**: fully open — `developer.axis.com` requires no registration for most content.

**Estimated volume**: ~600–1,000 chunks (VAPIX is extensive).

---

### 3.6 HID Global (Access Control)

| Source | Format | Location | Priority |
|--------|--------|----------|:--------:|
| HID VertX EVO Controllers HTTP API | PDF | REST API for V1000/V2000 controllers | **P0** |
| HID OSDP Implementation Guide | PDF | Open Supervised Device Protocol for readers | **P1** |
| HID Signo Reader Integration | PDF | Reader SDK and configuration | **P1** |
| HID Origo Mobile Access SDK | PDF / Web | Mobile credentials and Bluetooth LE access | **P2** |
| HID Mercury Controllers API | PDF | LP series controller integration | **P2** |

**Ingestion method**: PDF upload.

**Access**: partially public, full SDK docs require partner program registration.

**Estimated volume**: ~300–500 chunks.

---

### 3.7 Genetec (VMS Platform)

| Source | Format | Location | Priority |
|--------|--------|----------|:--------:|
| Security Center SDK (REST) | Swagger / Web | `developer.genetec.com` — Web SDK (REST API) | **P0** |
| Security Center .NET SDK | PDF | .NET SDK for deep integration | **P1** |
| Genetec Sipelia (Intercom) API | PDF | Intercom module integration | **P2** |
| Genetec AutoVu (LPR) API | PDF | License plate recognition module | **P2** |
| Genetec Clearance (Evidence) API | Web | Digital evidence management API | **P2** |

**Ingestion method**: Swagger import + PDF upload. Web scraper for online docs.

**Access**: `developer.genetec.com` — requires developer registration (free).

**Estimated volume**: ~400–700 chunks.

---

## 4. Tier B — High-Value Niche Vendors

Strong niche positions with developer communities that need better tooling.

| Vendor | Category | Key Documentation | Source | Format | Priority |
|--------|----------|------------------|--------|--------|:--------:|
| **Hanwha Vision** (ex-Samsung) | Video | Wisenet Open Platform API, SUNAPI (HTTP) | `developer.hanwhavision.com` | Web / PDF | **P1** |
| **Bosch Security** | Video + Access | BVIP API (camera HTTP), Access Manager API, Bosch VMS SDK | `community.boschsecurity.com` | PDF / Swagger | **P1** |
| **Milestone** | VMS | MIP SDK (Management Integration Platform), Transact API | `developer.milestonesys.com` | PDF / Web | **P1** |
| **IDIS** | Video NVR/VMS | IDIS Center SDK, DirectIP Protocol documentation | Partner portal | PDF | **P2** |
| **2N** (Axis subsidiary) | Intercom | 2N HTTP API — exceptionally well-documented REST API | `wiki.2n.com` | Web / PDF | **P1** |
| **Suprema** | Biometrics + Access | BioStar 2 REST API, BioStar 2 Device SDK | `developer.supremainc.com` | Swagger / PDF | **P1** |
| **ZKTeco** | Access + Time | ZKBio CVSecurity API, PUSH Protocol, ZKBio Access SDK | Developer portal | PDF | **P1** |
| **Verkada** | Cloud Video | Verkada REST API (cloud-managed cameras) | `apidocs.verkada.com` | Swagger / Web | **P2** |
| **Brivo** | Cloud Access | Brivo Access API (cloud-based access control) | Developer portal | Swagger | **P2** |
| **SALTO** | Access Control | SALTO SPACE API, SALTO KS (Keys as a Service) API | Partner portal | PDF / Swagger | **P2** |
| **ASSA ABLOY** | Access Control + Locks | Aperio API, CLIQ API, HID (subsidiary) | Partner portal | PDF | **P2** |
| **Commend** | Intercom | Commend Symphony API (professional intercom systems) | Partner portal | PDF | **P2** |

**Estimated total volume for Tier B**: ~2,000–4,000 chunks across all vendors.

---

## 5. Tier C — Protocols & Standards (Cross-Vendor Value)

Industry protocols used by dozens or hundreds of vendors. Indexing these provides value to **all** AI Mentor users regardless of which vendor's devices they integrate.

### 5.1 Video Surveillance Protocols

| Protocol | Description | Source | Format | Priority |
|----------|------------|--------|--------|:--------:|
| **ONVIF Core** | Open Network Video Interface Forum — device discovery, media profiles, PTZ, events, analytics | `onvif.org/profiles/` | WSDL / PDF | **P0** |
| **ONVIF Profile S** | Video streaming profile (mandatory for IP cameras) | `onvif.org/profiles/profile-s/` | PDF | **P0** |
| **ONVIF Profile T** | Advanced video streaming (H.265, imaging settings) | `onvif.org/profiles/profile-t/` | PDF | **P1** |
| **ONVIF Profile G** | Edge storage and retrieval (recording on device) | `onvif.org/profiles/profile-g/` | PDF | **P1** |
| **ONVIF Profile M** | Metadata and analytics configuration | `onvif.org/profiles/profile-m/` | PDF | **P1** |
| **ONVIF Profile A** | Access control profile | `onvif.org/profiles/profile-a/` | PDF | **P1** |
| **ONVIF Profile C** | Access control for door/credential management | `onvif.org/profiles/profile-c/` | PDF | **P2** |
| **ONVIF Profile D** | Access control for peripheral devices | `onvif.org/profiles/profile-d/` | PDF | **P2** |
| **RTSP** (RFC 7826) | Real-Time Streaming Protocol — session setup, play/pause/teardown | `tools.ietf.org/html/rfc7826` | RFC (text) | **P0** |
| **RTP/RTCP** (RFC 3550) | Real-time Transport Protocol — media payload delivery, timing, synchronization | `tools.ietf.org/html/rfc3550` | RFC (text) | **P1** |
| **RTSP over HTTP** | HTTP tunneling for RTSP streams through firewalls | Various vendor docs | PDF / Web | **P2** |
| **H.264/AVC** (ITU-T H.264) | Video codec — NAL units, SPS/PPS, profiles/levels (integration-relevant parts) | ITU-T / Wikipedia technical | PDF / Web | **P2** |
| **H.265/HEVC** (ITU-T H.265) | Next-gen video codec — integration parameters, RTSP negotiation | ITU-T / Wikipedia technical | PDF / Web | **P2** |
| **MJPEG over HTTP** | Motion JPEG streaming via HTTP multipart — simple camera streaming | Various vendor docs | Web | **P2** |
| **CGI (Common Gateway Interface)** | Legacy HTTP camera control (Axis, Dahua, many others use CGI-style APIs) | Vendor-specific | PDF / Web | **P1** |

### 5.2 Access Control Protocols

| Protocol | Description | Source | Format | Priority |
|----------|------------|--------|--------|:--------:|
| **OSDP v2** (SIA) | Open Supervised Device Protocol — reader ↔ controller communication (RS-485) | `securityindustry.org/osdp` | PDF | **P0** |
| **Wiegand** | Legacy access control wiring protocol (26/34/37-bit formats) | SIA / Technical references | PDF / Web | **P1** |
| **PSIA** (Physical Security Interoperability Alliance) | REST-based API standard for security devices (video, access, analytics) | `psialliance.org` | XML / PDF | **P1** |
| **PLAI** (Physical Logical Access Interoperability) | Standard for unifying physical and logical access credentials | SIA specification | PDF | **P2** |
| **FICAM** (Federal Identity, Credential, and Access Management) | US government access control standard (PIV, CAC cards) | `idmanagement.gov` | PDF / Web | **P2** |
| **iCLASS SE / SEOS** | HID credential protocols for secure identity (smart card, mobile) | HID Global docs | PDF | **P2** |
| **MIFARE** (NXP) | Smart card technology — Classic, DESFire, Plus (widely used in access control) | NXP technical docs | PDF | **P2** |

### 5.3 Intercom & Communication Protocols

| Protocol | Description | Source | Format | Priority |
|----------|------------|--------|--------|:--------:|
| **SIP** (RFC 3261) | Session Initiation Protocol — VoIP/video calling for intercoms | `tools.ietf.org/html/rfc3261` | RFC (text) | **P0** |
| **SDP** (RFC 8866) | Session Description Protocol — media negotiation (used with SIP and RTSP) | `tools.ietf.org/html/rfc8866` | RFC (text) | **P1** |
| **RTP Audio Codecs** | G.711 (PCM), G.722 (wideband), G.729 (compressed) — intercom audio | ITU-T specs | PDF | **P2** |
| **DTMF** (RFC 4733) | Dual-Tone Multi-Frequency — door release signals via SIP | IETF | RFC (text) | **P2** |

### 5.4 Building Automation & IoT Protocols

| Protocol | Description | Source | Format | Priority |
|----------|------------|--------|--------|:--------:|
| **BACnet** (ASHRAE 135) | Building Automation and Control network — HVAC, lighting, fire, access | `bacnet.org` | PDF | **P1** |
| **Modbus** (TCP/RTU) | Industrial communication protocol — sensors, controllers, PLCs | `modbus.org/specs` | PDF | **P1** |
| **MQTT** (v5.0 / v3.1.1) | Lightweight IoT messaging (pub/sub) — sensors, telemetry, events | `mqtt.org`, `docs.oasis-open.org` | Web / PDF | **P1** |
| **OPC UA** (IEC 62541) | Open Platform Communications Unified Architecture — industrial interoperability | `opcfoundation.org` | PDF / Web | **P1** |
| **KNX** | European building automation standard (lighting, HVAC, blinds, security) | `knx.org` | PDF | **P2** |
| **LonWorks** (ISO/IEC 14908) | Building automation networking protocol | Echelon / ISO | PDF | **P2** |
| **SNMP** (v2c/v3) | Simple Network Management Protocol — device monitoring, health, status | RFC 3416/3414 | RFC (text) | **P1** |
| **CoAP** (RFC 7252) | Constrained Application Protocol — lightweight IoT REST-like protocol | `tools.ietf.org/html/rfc7252` | RFC (text) | **P2** |
| **AMQP** (v1.0) | Advanced Message Queuing Protocol — enterprise messaging (Azure IoT Hub) | `amqp.org` | PDF / Web | **P2** |
| **Zigbee** (IEEE 802.15.4) | Low-power wireless mesh — sensors, smart locks, lighting | `csa-iot.org` (Zigbee Alliance) | PDF | **P2** |
| **Z-Wave** | Smart home wireless protocol — locks, sensors, thermostats | `z-wavealliance.org` | PDF | **P2** |
| **Thread / Matter** | Next-gen smart home IP protocol (Google, Apple, Amazon backed) | `csa-iot.org/matter` | Web / PDF | **P2** |

### 5.5 Network & Discovery Protocols

| Protocol | Description | Source | Format | Priority |
|----------|------------|--------|--------|:--------:|
| **UPnP / SSDP** | Universal Plug and Play / Simple Service Discovery — device auto-discovery on LAN | UPnP Forum specs | PDF | **P1** |
| **mDNS / DNS-SD** (RFC 6762/6763) | Multicast DNS / Service Discovery — zero-config device discovery (Bonjour) | IETF | RFC (text) | **P1** |
| **LLDP** (IEEE 802.1AB) | Link Layer Discovery Protocol — network topology, PoE negotiation | IEEE | PDF | **P2** |
| **DHCP Options** (RFC 2132) | DHCP vendor-specific options for IP camera auto-provisioning | IETF | RFC (text) | **P2** |
| **IEEE 802.1X** | Port-based Network Access Control — NAC for IP devices | IEEE | PDF | **P1** |
| **TLS / mTLS** | Transport Layer Security — encrypted communication, mutual authentication | IETF RFCs | RFC (text) | **P1** |

### 5.6 Data Exchange & Integration Standards

| Standard | Description | Source | Format | Priority |
|----------|------------|--------|--------|:--------:|
| **OSLP** (Open Smart Lighting Protocol) | Smart city lighting control | OSGP Alliance | PDF | **P2** |
| **CZML / KML** | Geospatial data for map-based security visualization | OGC / Google | Web / JSON | **P2** |
| **GeoJSON** (RFC 7946) | Geospatial data exchange — camera/sensor locations on maps | IETF | RFC (text) | **P2** |
| **STIX / TAXII** | Threat intelligence sharing (cybersecurity integration) | OASIS | PDF / Web | **P2** |
| **OpenAPI 3.1** | API description standard — many vendors publish Swagger/OpenAPI specs | `spec.openapis.org` | YAML / JSON | **P0** |
| **AsyncAPI** | API description for event-driven architectures (WebSocket, MQTT, AMQP) | `asyncapi.com` | YAML / JSON | **P2** |
| **JSON:API** | JSON-based API specification (some VMS platforms follow this) | `jsonapi.org` | Web | **P2** |
| **gRPC / Protocol Buffers** | RPC framework and serialization — used by Axxon One, Google, others | `grpc.io`, `protobuf.dev` | Web / Proto | **P1** |

**Estimated total volume for Tier C**: ~3,000–5,000 chunks across all protocols and standards.

---

## 6. Tier D — Long-Tail Vendors (Catalog Mass)

Index public documentation from any vendor with available API/integration docs. These are Content Partners (free tier) — no vendor relationship needed.

### Video Surveillance

| Vendor | Region | Notable Products | Doc Availability |
|--------|--------|-----------------|:----------------:|
| Vivotek | Taiwan | IP cameras, NVR | Public PDF |
| Uniview | China | IP cameras, NVR (fast-growing) | Partner portal |
| Pelco (Motorola) | USA | Legacy cameras, VMS (Endura/VX) | Public PDF |
| Avigilon (Motorola) | Canada | AI-powered cameras, ACC VMS | Developer portal |
| FLIR (Teledyne) | USA | Thermal cameras, FLIR Latitude VMS | Public PDF |
| Mobotix | Germany | Decentralized cameras (in-camera storage) | `developer.mobotix.com` |
| Milesight | China | IoT + Video, LoRaWAN cameras | Public PDF |
| Wisenet (Hanwha) | Korea | See Tier B above | — |
| Tiandy | China | AI cameras, NVR | Limited public docs |
| TVT Digital | China | Budget IP cameras, HTTP API | Public PDF |

### Access Control

| Vendor | Region | Notable Products | Doc Availability |
|--------|--------|-----------------|:----------------:|
| Honeywell | USA | Pro-Watch, WIN-PAK, access controllers | Partner portal |
| Gallagher | New Zealand | Command Centre — enterprise access control | Partner portal |
| Paxton | UK | Net2, Paxton10 — popular in Europe | `developers.paxton.co.uk` |
| Lenel (Carrier) | USA | OnGuard, S2 — enterprise PACS | Partner portal |
| LenelS2 | USA | Merged Lenel + S2, NetBox API | Partner portal |
| Nedap | Netherlands | AEOS access control platform | Partner portal |
| Keri Systems | USA | NXT controllers, Doors.NET | Public PDF |
| DoorBird | Germany | IP Video Doorbell — well-documented HTTP API | `doorbird.com/api` |

### Intercom Systems

| Vendor | Region | Notable Products | Doc Availability |
|--------|--------|-----------------|:----------------:|
| Comelit | Italy | IP intercom systems (European leader) | Partner portal |
| Aiphone | Japan | IX series IP intercoms, SIP-based | Public PDF |
| BAS-IP | Ukraine/Global | SIP intercoms, open HTTP API | `bas-ip.com/api` |
| Akuvox | China | SIP intercoms, Android-based | Developer portal |
| Mobotix (BellRFID) | Germany | Door stations with RFID | See Mobotix above |

### Analytics & Sensors

| Vendor | Region | Notable Products | Doc Availability |
|--------|--------|-----------------|:----------------:|
| Agent Vi (Caliber) | Israel | Video analytics (crowd, perimeter, traffic) | Partner portal |
| BriefCam (Canon) | Israel | Video synopsis and analytics | Partner portal |
| Optex | Japan | Laser/IR/LIDAR sensors for perimeter detection | Public PDF |
| Senstar | Canada | Perimeter intrusion detection (fence, buried cable) | Public PDF |
| LILIN | Taiwan | Video analytics, IP cameras | Public PDF |

**Estimated total volume for Tier D**: ~5,000–15,000 chunks depending on coverage depth.

---

## 7. Ingestion Roadmap

### Week 1–4: Foundation Content

```
Goal: 5–7 vendors indexed, 30+ documents, 2,000+ chunks
      Platform has enough content for meaningful developer experience

PRIORITY ACTIONS:
  1. AxxonSoft Confluence      → confluence.py crawler (P0)
     - Axxon One HTTP API
     - Axxon One gRPC API
     - Axxon One WebSocket API
     Estimated: 300–500 chunks

  2. Axis VAPIX               → web.py scraper (P0)
     - developer.axis.com/vapix pages
     - PTZ, streaming, events, analytics sections
     Estimated: 400–600 chunks

  3. ONVIF Core Specs          → PDF upload (P0)
     - Profile S, Profile T (video streaming)
     - Core specification (device discovery, events)
     Estimated: 200–400 chunks

  4. Hikvision ISAPI           → PDF upload (P0)
     - Main ISAPI document (200+ pages)
     - HikCentral Open API if available
     Estimated: 500–800 chunks

  5. RTSP RFC 7826             → web/markdown import (P0)
     - Streaming protocol used by all IP cameras
     Estimated: 50–100 chunks

  6. OpenAPI 3.1 Spec          → web import (P0)
     - Standard reference for API documentation
     Estimated: 50–100 chunks

SUCCESS CRITERIA:
  - A developer can ask "How to stream video from Axis camera?" and get relevant answer
  - A developer can ask "How to use Axxon One HTTP API?" and get working code context
  - ONVIF PTZ queries return accurate protocol details
```

### Month 2–3: Expansion

```
Goal: 15–20 vendors indexed, 100+ documents, 5,000+ chunks
      Cross-vendor queries work (e.g., "compare Hikvision vs Dahua API")

PRIORITY ACTIONS:
  1. Grundig SMART Line        → PDF upload via partner contact (P0)
  2. Dahua HTTP API            → PDF upload (P0)
  3. Genetec Security Center   → Swagger + PDF (P1)
  4. Milestone MIP SDK         → PDF + web scraper (P1)
  5. 2N HTTP API               → web scraper (P1) — wiki.2n.com
  6. HID VertX EVO API         → PDF upload (P1)
  7. OSDP v2 Specification     → PDF upload (P0)
  8. SIP RFC 3261              → web/markdown import (P0)
  9. BACnet Overview           → PDF upload (P1)
  10. Modbus TCP/RTU           → PDF upload (P1)
  11. Suprema BioStar 2 API   → Swagger import (P1)
  12. ZKTeco PUSH Protocol     → PDF upload (P1)

TIER B VENDORS (parallel):
  - Hanwha Vision SUNAPI
  - Bosch BVIP API
  - Verkada REST API

SUCCESS CRITERIA:
  - Cross-vendor comparison queries work
  - Access control (HID, OSDP, ZKTeco) is searchable
  - Intercom protocols (SIP, 2N) are indexed
```

### Month 3–6: Catalog Mass

```
Goal: 50–100 vendors indexed, 500+ documents, 15,000+ chunks
      Platform is the most comprehensive device documentation search tool

PRIORITY ACTIONS:
  1. Tier D vendors — bulk index public PDFs from vendor websites
  2. Remaining Tier C protocols — IoT, building automation, network discovery
  3. Tier B remaining vendors — IDIS, Verkada, Brivo, SALTO, ASSA ABLOY, Commend
  4. Additional Tier A docs — deep coverage (every API endpoint, every SDK method)

AUTOMATION:
  - Scripted download of public PDFs from vendor sites
  - Batch upload via CLI (scripts/upload_document.py)
  - Archive upload for multi-file vendor SDKs (ZIP/7z)

SUCCESS CRITERIA:
  - "List all available cameras with LPR" returns results from 5+ vendors
  - Protocol queries (ONVIF, OSDP, BACnet, SIP) consistently accurate
  - Any top-50 security vendor has at least basic documentation indexed
```

---

## 8. Content Acquisition Methods

| Method | Effort | Legal Risk | Best For |
|--------|:------:|:----------:|----------|
| **Confluence crawler** | Low | None (partner) | AxxonSoft, vendors with Confluence docs |
| **Web scraper** | Low | Low (public docs) | Axis, 2N, Milestone, Hanwha — developer portals |
| **PDF download from public sites** | Low | Low (public docs) | Most vendors publish PDFs on support/download pages |
| **Partner portal access** | Medium | None (registered) | Hikvision, Dahua, HID — register as developer/integrator |
| **Direct from vendor** | Medium | None (partnership) | Grundig, future Tier 2–3 partners — docs sent by email or shared drive |
| **Swagger/OpenAPI export** | Low | Low | Genetec, Suprema, Verkada — developer portals often expose specs |
| **RFC/Standards download** | Low | None (public) | IETF RFCs, ONVIF, OSDP — fully open specifications |
| **GitHub repositories** | Low | Check license | ONVIF tools, open-source SDK wrappers, community examples |
| **Archive (ZIP/7z) upload** | Low | Varies | SDK packages, multi-file documentation sets |

### Legal Considerations

- **Public documentation** (vendor websites, developer portals): generally safe to index for search purposes. Similar to how Google indexes web pages.
- **Partner portal documentation**: covered by partner/developer agreement. Most allow use for integration purposes.
- **Standards (IETF RFC, ONVIF)**: published as open standards, free to reference and index.
- **Vendor SDKs with license agreements**: review license terms. Most allow use for integration development.
- When in doubt: reach out to vendor and offer Content Partner status (free) — most vendors welcome better discoverability.

---

## 9. Content Quality Metrics

Track per-vendor and per-document quality to prioritize improvement:

| Metric | Target | How to Measure |
|--------|:------:|---------------|
| Chunks per vendor | 100–500 (meaningful coverage) | `SELECT product_id, COUNT(*) FROM chunks GROUP BY product_id` |
| Avg similarity score (top-5 results) | > 0.45 | `search_analytics.avg_similarity` |
| Zero-result query rate per vendor | < 15% | Queries with 0 results / total queries per vendor |
| OCR quality (for scanned PDFs) | < 5% failed images | `documents.ocr_images_failed / ocr_images_total` |
| Chunk token distribution | 80–400 tokens (sweet spot) | Ingestion quality logs (min/max/avg/median) |
| Stale document rate | 0% (all docs current) | Documents with `indexed_at` > 6 months ago |

---

## 10. Summary

| Tier | Vendors | Estimated Chunks | Timeline | Status |
|:----:|:-------:|:----------------:|:--------:|:------:|
| **A** — Founding + Leaders | 7 | 3,000–5,500 | Week 1–4 | Planned |
| **B** — High-Value Niche | 12 | 2,000–4,000 | Month 2–3 | Planned |
| **C** — Protocols & Standards | 40+ specs | 3,000–5,000 | Month 1–3 | Planned |
| **D** — Long-Tail Catalog | 50–100 | 5,000–15,000 | Month 3–6 | Planned |
| **Total** | **70–120+** | **13,000–30,000** | **6 months** | — |

At projected scale, AI Mentor will contain the most comprehensive AI-searchable database of physical security device documentation — covering the major vendors, industry protocols, and integration standards that developers work with daily.
