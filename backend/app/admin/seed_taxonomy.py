"""Seed product categories, tags, taxonomy translations, and search keywords.

Called at application startup (lifespan). All inserts use ON CONFLICT
so the seed is idempotent. System entries (is_system=True) are updated
from code; non-system entries created by admins are left untouched.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

CATEGORIES: list[dict] = [
    {"slug": "video_surveillance", "icon": "📹", "sort_order": 0},
    {"slug": "access_control", "icon": "🛡️", "sort_order": 1},
    {"slug": "intercom", "icon": "📞", "sort_order": 2},
    {"slug": "alarm_intrusion", "icon": "🔔", "sort_order": 3},
    {"slug": "building_automation", "icon": "🏢", "sort_order": 4},
    {"slug": "software", "icon": "🖥️", "sort_order": 5},
    {"slug": "protocols", "icon": "🌐", "sort_order": 6},
]

CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "video_surveillance": {"en": "Video Surveillance", "ru": "Видеонаблюдение"},
    "access_control": {"en": "Access Control", "ru": "Контроль доступа"},
    "intercom": {"en": "Intercom", "ru": "Домофония"},
    "alarm_intrusion": {"en": "Alarm & Intrusion", "ru": "Охранная сигнализация"},
    "building_automation": {"en": "Building Automation", "ru": "Автоматизация зданий"},
    "software": {"en": "Software & VMS", "ru": "ПО и видеоменеджмент"},
    "protocols": {"en": "Protocols & Standards", "ru": "Протоколы и стандарты"},
}

TAGS: list[str] = [
    # Video protocols & codecs
    "onvif", "rtsp", "rtmp", "hls", "webrtc",
    "h264", "h265", "mjpeg", "aac", "g711",
    # Network protocols
    "sip", "osdp", "bacnet", "modbus", "knx",
    "mqtt", "amqp", "snmp", "ntp", "dhcp",
    "http-api", "rest-api", "soap", "grpc", "websocket",
    # Video features
    "ptz", "lpr", "anpr", "face-recognition", "edge-ai",
    "motion-detection", "line-crossing", "intrusion-detection", "people-counting", "heat-map",
    "fisheye", "panoramic", "multi-sensor", "thermal", "ir",
    # Access control
    "card-reader", "biometric", "fingerprint", "qr-code", "mobile-access",
    "elevator-control", "anti-passback", "visitor-management", "time-attendance", "interlock",
    # Intercom & audio
    "two-way-audio", "door-station", "indoor-monitor", "emergency-call", "broadcast",
    # Building automation
    "hvac", "lighting-control", "energy-management", "fire-alarm", "bms-integration",
    # Software & platforms
    "vms", "cms", "psim", "cloud-platform", "mobile-app",
    "sdk", "plugin", "open-api", "webhook", "event-subscription",
    # General
    "firmware-upgrade", "configuration", "installation-guide", "troubleshooting", "data-sheet",
    "cybersecurity", "tls-ssl", "ieee-802-1x", "digest-auth", "certificate-management",
]

TAG_LABELS: dict[str, dict[str, str]] = {
    "onvif": {"en": "ONVIF", "ru": "ONVIF"},
    "rtsp": {"en": "RTSP", "ru": "RTSP"},
    "rtmp": {"en": "RTMP", "ru": "RTMP"},
    "hls": {"en": "HLS", "ru": "HLS"},
    "webrtc": {"en": "WebRTC", "ru": "WebRTC"},
    "h264": {"en": "H.264", "ru": "H.264"},
    "h265": {"en": "H.265 / HEVC", "ru": "H.265 / HEVC"},
    "mjpeg": {"en": "MJPEG", "ru": "MJPEG"},
    "aac": {"en": "AAC", "ru": "AAC"},
    "g711": {"en": "G.711", "ru": "G.711"},
    "sip": {"en": "SIP", "ru": "SIP"},
    "osdp": {"en": "OSDP", "ru": "OSDP"},
    "bacnet": {"en": "BACnet", "ru": "BACnet"},
    "modbus": {"en": "Modbus", "ru": "Modbus"},
    "knx": {"en": "KNX", "ru": "KNX"},
    "mqtt": {"en": "MQTT", "ru": "MQTT"},
    "amqp": {"en": "AMQP", "ru": "AMQP"},
    "snmp": {"en": "SNMP", "ru": "SNMP"},
    "ntp": {"en": "NTP", "ru": "NTP"},
    "dhcp": {"en": "DHCP", "ru": "DHCP"},
    "http-api": {"en": "HTTP API", "ru": "HTTP API"},
    "rest-api": {"en": "REST API", "ru": "REST API"},
    "soap": {"en": "SOAP", "ru": "SOAP"},
    "grpc": {"en": "gRPC", "ru": "gRPC"},
    "websocket": {"en": "WebSocket", "ru": "WebSocket"},
    "ptz": {"en": "PTZ", "ru": "PTZ"},
    "lpr": {"en": "LPR", "ru": "Распознавание номеров"},
    "anpr": {"en": "ANPR", "ru": "ANPR"},
    "face-recognition": {"en": "Face Recognition", "ru": "Распознавание лиц"},
    "edge-ai": {"en": "Edge AI", "ru": "Edge AI"},
    "motion-detection": {"en": "Motion Detection", "ru": "Детектор движения"},
    "line-crossing": {"en": "Line Crossing", "ru": "Пересечение линии"},
    "intrusion-detection": {"en": "Intrusion Detection", "ru": "Детектор вторжения"},
    "people-counting": {"en": "People Counting", "ru": "Подсчёт людей"},
    "heat-map": {"en": "Heat Map", "ru": "Тепловая карта"},
    "fisheye": {"en": "Fisheye", "ru": "Рыбий глаз"},
    "panoramic": {"en": "Panoramic", "ru": "Панорамная"},
    "multi-sensor": {"en": "Multi-Sensor", "ru": "Мультисенсорная"},
    "thermal": {"en": "Thermal", "ru": "Тепловизор"},
    "ir": {"en": "IR Night Vision", "ru": "ИК подсветка"},
    "card-reader": {"en": "Card Reader", "ru": "Считыватель карт"},
    "biometric": {"en": "Biometric", "ru": "Биометрия"},
    "fingerprint": {"en": "Fingerprint", "ru": "Отпечаток пальца"},
    "qr-code": {"en": "QR Code", "ru": "QR-код"},
    "mobile-access": {"en": "Mobile Access", "ru": "Мобильный доступ"},
    "elevator-control": {"en": "Elevator Control", "ru": "Управление лифтом"},
    "anti-passback": {"en": "Anti-Passback", "ru": "Anti-Passback"},
    "visitor-management": {"en": "Visitor Management", "ru": "Управление посетителями"},
    "time-attendance": {"en": "Time & Attendance", "ru": "Учёт рабочего времени"},
    "interlock": {"en": "Interlock", "ru": "Шлюз"},
    "two-way-audio": {"en": "Two-Way Audio", "ru": "Двусторонняя связь"},
    "door-station": {"en": "Door Station", "ru": "Вызывная панель"},
    "indoor-monitor": {"en": "Indoor Monitor", "ru": "Внутренний монитор"},
    "emergency-call": {"en": "Emergency Call", "ru": "Экстренный вызов"},
    "broadcast": {"en": "Broadcast", "ru": "Оповещение"},
    "hvac": {"en": "HVAC", "ru": "ОВК"},
    "lighting-control": {"en": "Lighting Control", "ru": "Управление освещением"},
    "energy-management": {"en": "Energy Management", "ru": "Энергоменеджмент"},
    "fire-alarm": {"en": "Fire Alarm", "ru": "Пожарная сигнализация"},
    "bms-integration": {"en": "BMS Integration", "ru": "Интеграция с BMS"},
    "vms": {"en": "VMS", "ru": "Видеоменеджмент"},
    "cms": {"en": "CMS", "ru": "CMS"},
    "psim": {"en": "PSIM", "ru": "PSIM"},
    "cloud-platform": {"en": "Cloud Platform", "ru": "Облачная платформа"},
    "mobile-app": {"en": "Mobile App", "ru": "Мобильное приложение"},
    "sdk": {"en": "SDK", "ru": "SDK"},
    "plugin": {"en": "Plugin", "ru": "Плагин"},
    "open-api": {"en": "Open API", "ru": "Open API"},
    "webhook": {"en": "Webhook", "ru": "Webhook"},
    "event-subscription": {"en": "Event Subscription", "ru": "Подписка на события"},
    "firmware-upgrade": {"en": "Firmware Upgrade", "ru": "Обновление прошивки"},
    "configuration": {"en": "Configuration", "ru": "Настройка"},
    "installation-guide": {"en": "Installation Guide", "ru": "Руководство по установке"},
    "troubleshooting": {"en": "Troubleshooting", "ru": "Устранение неполадок"},
    "data-sheet": {"en": "Data Sheet", "ru": "Спецификация"},
    "cybersecurity": {"en": "Cybersecurity", "ru": "Кибербезопасность"},
    "tls-ssl": {"en": "TLS/SSL", "ru": "TLS/SSL"},
    "ieee-802-1x": {"en": "IEEE 802.1X", "ru": "IEEE 802.1X"},
    "digest-auth": {"en": "Digest Auth", "ru": "Digest-аутентификация"},
    "certificate-management": {"en": "Certificate Management", "ru": "Управление сертификатами"},
}


async def seed_taxonomy(session: AsyncSession) -> None:
    """Seed categories, tags, and their translations."""
    await _seed_categories(session)
    await _seed_tags(session)
    await _seed_taxonomy_translations(session)
    await session.commit()
    logger.info("Taxonomy seed complete")


async def _seed_categories(session: AsyncSession) -> None:
    for cat in CATEGORIES:
        await session.execute(
            text(
                "INSERT INTO product_categories (slug, icon, sort_order, is_system) "
                "VALUES (:slug, :icon, :sort_order, TRUE) "
                "ON CONFLICT (slug) DO UPDATE SET "
                "icon = EXCLUDED.icon, sort_order = EXCLUDED.sort_order"
            ),
            cat,
        )
    logger.info("Seeded categories", extra={"count": len(CATEGORIES)})


async def _seed_tags(session: AsyncSession) -> None:
    for slug in TAGS:
        await session.execute(
            text(
                "INSERT INTO tags (slug, is_system) "
                "VALUES (:slug, TRUE) "
                "ON CONFLICT (slug) DO NOTHING"
            ),
            {"slug": slug},
        )
    logger.info("Seeded tags", extra={"count": len(TAGS)})


async def _seed_taxonomy_translations(session: AsyncSession) -> None:
    lang_rows = await session.execute(
        text("SELECT id, code FROM languages WHERE code IN ('en', 'ru')")
    )
    lang_map = {r.code: r.id for r in lang_rows}
    if "en" not in lang_map or "ru" not in lang_map:
        logger.warning("System languages not found, skipping taxonomy translations")
        return

    count = 0
    for slug, labels in CATEGORY_LABELS.items():
        for lang_code, value in labels.items():
            await session.execute(
                text(
                    "INSERT INTO translations (language_id, namespace, key, value, is_system) "
                    "VALUES (:lid, 'taxonomy', :key, :value, TRUE) "
                    "ON CONFLICT (language_id, namespace, key) DO UPDATE SET "
                    "value = EXCLUDED.value, updated_at = NOW() "
                    "WHERE translations.is_modified = false"
                ),
                {"lid": lang_map[lang_code], "key": f"category.{slug}", "value": value},
            )
            count += 1

    for slug, labels in TAG_LABELS.items():
        for lang_code, value in labels.items():
            await session.execute(
                text(
                    "INSERT INTO translations (language_id, namespace, key, value, is_system) "
                    "VALUES (:lid, 'taxonomy', :key, :value, TRUE) "
                    "ON CONFLICT (language_id, namespace, key) DO UPDATE SET "
                    "value = EXCLUDED.value, updated_at = NOW() "
                    "WHERE translations.is_modified = false"
                ),
                {"lid": lang_map[lang_code], "key": f"tag.{slug}", "value": value},
            )
            count += 1

    logger.info("Seeded taxonomy translations", extra={"count": count})
