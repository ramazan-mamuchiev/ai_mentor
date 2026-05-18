"""WSDL -> Markdown converter.

Parses WSDL 1.1 XML and generates structured Markdown with:
- Service name and target namespace
- Port types and operations (input/output messages)
- Message definitions with parts and types
- Complex type definitions
- Bindings (SOAP actions, transport)
"""

import logging
import os
import time
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

_WSDL_NS = "http://schemas.xmlsoap.org/wsdl/"
_SOAP_NS = "http://schemas.xmlsoap.org/wsdl/soap/"
_SOAP12_NS = "http://schemas.xmlsoap.org/wsdl/soap12/"
_XSD_NS = "http://www.w3.org/2001/XMLSchema"

_NS_MAP = {
    "wsdl": _WSDL_NS,
    "soap": _SOAP_NS,
    "soap12": _SOAP12_NS,
    "xsd": _XSD_NS,
}


def _strip_ns(tag: str) -> str:
    """Remove namespace prefix from an XML tag."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _local_name(qname: str | None) -> str:
    """Extract local part from a QName like 'tns:GetDeviceInfo'."""
    if not qname:
        return ""
    return qname.split(":", 1)[-1]


def _find_all(root: ET.Element, ns: str, local: str) -> list[ET.Element]:
    return root.findall(f"{{{ns}}}{local}")


def _find(root: ET.Element, ns: str, local: str) -> ET.Element | None:
    return root.find(f"{{{ns}}}{local}")


def _parse_xsd_types(root: ET.Element) -> list[dict]:
    """Extract XSD complex/simple type definitions from <wsdl:types>."""
    types_el = _find(root, _WSDL_NS, "types")
    if types_el is None:
        return []

    result: list[dict] = []

    for schema in types_el.iter(f"{{{_XSD_NS}}}schema"):
        target_ns = schema.get("targetNamespace", "")

        for ct in schema.iter(f"{{{_XSD_NS}}}complexType"):
            name = ct.get("name", "(anonymous)")
            elements: list[dict] = []
            for el in ct.iter(f"{{{_XSD_NS}}}element"):
                elements.append({
                    "name": el.get("name", ""),
                    "type": _local_name(el.get("type", "")),
                    "min": el.get("minOccurs", ""),
                    "max": el.get("maxOccurs", ""),
                })
            result.append({
                "kind": "complexType",
                "name": name,
                "namespace": target_ns,
                "elements": elements,
            })

        for st in schema.iter(f"{{{_XSD_NS}}}simpleType"):
            name = st.get("name", "(anonymous)")
            restriction = st.find(f"{{{_XSD_NS}}}restriction")
            base = _local_name(restriction.get("base", "")) if restriction is not None else ""
            enums = [e.get("value", "") for e in st.iter(f"{{{_XSD_NS}}}enumeration")]
            result.append({
                "kind": "simpleType",
                "name": name,
                "namespace": target_ns,
                "base": base,
                "enums": enums,
            })

        for elem in schema.findall(f"{{{_XSD_NS}}}element"):
            name = elem.get("name", "")
            elem_type = _local_name(elem.get("type", ""))
            inner_ct = elem.find(f"{{{_XSD_NS}}}complexType")
            if inner_ct is not None:
                elements: list[dict] = []
                for el in inner_ct.iter(f"{{{_XSD_NS}}}element"):
                    elements.append({
                        "name": el.get("name", ""),
                        "type": _local_name(el.get("type", "")),
                        "min": el.get("minOccurs", ""),
                        "max": el.get("maxOccurs", ""),
                    })
                result.append({
                    "kind": "element",
                    "name": name,
                    "namespace": target_ns,
                    "type": elem_type,
                    "elements": elements,
                })
            elif elem_type:
                result.append({
                    "kind": "element",
                    "name": name,
                    "namespace": target_ns,
                    "type": elem_type,
                    "elements": [],
                })

    return result


def _parse_messages(root: ET.Element) -> dict[str, list[dict]]:
    """Parse <wsdl:message> definitions. Returns {message_name: [parts]}."""
    messages: dict[str, list[dict]] = {}
    for msg in _find_all(root, _WSDL_NS, "message"):
        name = msg.get("name", "")
        parts: list[dict] = []
        for part in _find_all(msg, _WSDL_NS, "part"):
            parts.append({
                "name": part.get("name", ""),
                "element": _local_name(part.get("element", "")),
                "type": _local_name(part.get("type", "")),
            })
        messages[name] = parts
    return messages


def _parse_port_types(root: ET.Element) -> list[dict]:
    """Parse <wsdl:portType> with operations."""
    port_types: list[dict] = []
    for pt in _find_all(root, _WSDL_NS, "portType"):
        name = pt.get("name", "")
        operations: list[dict] = []
        for op in _find_all(pt, _WSDL_NS, "operation"):
            inp = _find(op, _WSDL_NS, "input")
            out = _find(op, _WSDL_NS, "output")
            faults = _find_all(op, _WSDL_NS, "fault")
            doc_el = _find(op, _WSDL_NS, "documentation")
            operations.append({
                "name": op.get("name", ""),
                "doc": (doc_el.text or "").strip() if doc_el is not None else "",
                "input": _local_name(inp.get("message", "")) if inp is not None else "",
                "output": _local_name(out.get("message", "")) if out is not None else "",
                "faults": [
                    {"name": f.get("name", ""), "message": _local_name(f.get("message", ""))}
                    for f in faults
                ],
            })
        port_types.append({"name": name, "operations": operations})
    return port_types


def _parse_bindings(root: ET.Element) -> list[dict]:
    """Parse <wsdl:binding> with SOAP actions."""
    bindings: list[dict] = []
    for bind in _find_all(root, _WSDL_NS, "binding"):
        name = bind.get("name", "")
        port_type = _local_name(bind.get("type", ""))

        transport = ""
        style = ""
        for ns in (_SOAP_NS, _SOAP12_NS):
            soap_binding = _find(bind, ns, "binding")
            if soap_binding is not None:
                transport = soap_binding.get("transport", "")
                style = soap_binding.get("style", "")
                break

        operations: list[dict] = []
        for op in _find_all(bind, _WSDL_NS, "operation"):
            soap_action = ""
            for ns in (_SOAP_NS, _SOAP12_NS):
                soap_op = _find(op, ns, "operation")
                if soap_op is not None:
                    soap_action = soap_op.get("soapAction", "")
                    break
            operations.append({
                "name": op.get("name", ""),
                "soap_action": soap_action,
            })

        bindings.append({
            "name": name,
            "port_type": port_type,
            "transport": transport,
            "style": style,
            "operations": operations,
        })
    return bindings


def _parse_services(root: ET.Element) -> list[dict]:
    """Parse <wsdl:service> with ports."""
    services: list[dict] = []
    for svc in _find_all(root, _WSDL_NS, "service"):
        name = svc.get("name", "")
        ports: list[dict] = []
        for port in _find_all(svc, _WSDL_NS, "port"):
            address = ""
            for ns in (_SOAP_NS, _SOAP12_NS):
                addr_el = _find(port, ns, "address")
                if addr_el is not None:
                    address = addr_el.get("location", "")
                    break
            ports.append({
                "name": port.get("name", ""),
                "binding": _local_name(port.get("binding", "")),
                "address": address,
            })
        services.append({"name": name, "ports": ports})
    return services


def _to_markdown(
    target_ns: str,
    services: list[dict],
    port_types: list[dict],
    messages: dict[str, list[dict]],
    bindings: list[dict],
    xsd_types: list[dict],
    filename: str,
) -> str:
    """Render parsed WSDL structures as Markdown."""
    lines: list[str] = []

    title = services[0]["name"] if services else os.path.splitext(filename)[0]
    lines.append(f"# {title}")
    lines.append("")
    if target_ns:
        lines.append(f"**Target namespace**: `{target_ns}`")
        lines.append("")

    if services:
        lines.append("## Services")
        lines.append("")
        for svc in services:
            lines.append(f"### {svc['name']}")
            lines.append("")
            for port in svc["ports"]:
                lines.append(f"- **Port** `{port['name']}` — binding: `{port['binding']}`")
                if port["address"]:
                    lines.append(f"  - Address: `{port['address']}`")
            lines.append("")

    for pt in port_types:
        lines.append(f"## Port Type: {pt['name']}")
        lines.append("")
        if not pt["operations"]:
            lines.append("No operations defined.")
            lines.append("")
            continue

        lines.append(f"| Operation | Input | Output |")
        lines.append(f"|-----------|-------|--------|")
        for op in pt["operations"]:
            lines.append(f"| `{op['name']}` | `{op['input']}` | `{op['output']}` |")
        lines.append("")

        for op in pt["operations"]:
            lines.append(f"### {op['name']}")
            lines.append("")
            if op["doc"]:
                lines.append(f"{op['doc']}")
                lines.append("")
            lines.append(f"- **Input message**: `{op['input']}`")
            lines.append(f"- **Output message**: `{op['output']}`")
            if op["faults"]:
                for f in op["faults"]:
                    lines.append(f"- **Fault** `{f['name']}`: `{f['message']}`")
            lines.append("")

    if bindings:
        lines.append("## Bindings")
        lines.append("")
        for bind in bindings:
            lines.append(f"### {bind['name']}")
            lines.append("")
            lines.append(f"- Port type: `{bind['port_type']}`")
            if bind["transport"]:
                lines.append(f"- Transport: `{bind['transport']}`")
            if bind["style"]:
                lines.append(f"- Style: `{bind['style']}`")
            lines.append("")
            if bind["operations"]:
                lines.append("| Operation | SOAP Action |")
                lines.append("|-----------|-------------|")
                for op in bind["operations"]:
                    lines.append(f"| `{op['name']}` | `{op['soap_action']}` |")
                lines.append("")

    referenced_messages: set[str] = set()
    for pt in port_types:
        for op in pt["operations"]:
            if op["input"]:
                referenced_messages.add(op["input"])
            if op["output"]:
                referenced_messages.add(op["output"])
            for f in op["faults"]:
                if f["message"]:
                    referenced_messages.add(f["message"])

    relevant_messages = {k: v for k, v in messages.items() if k in referenced_messages}
    if relevant_messages:
        lines.append("## Messages")
        lines.append("")
        for msg_name, parts in sorted(relevant_messages.items()):
            lines.append(f"### {msg_name}")
            lines.append("")
            if parts:
                lines.append("| Part | Element / Type |")
                lines.append("|------|----------------|")
                for p in parts:
                    ref = p["element"] or p["type"] or "—"
                    lines.append(f"| `{p['name']}` | `{ref}` |")
                lines.append("")
            else:
                lines.append("No parts.")
                lines.append("")

    if xsd_types:
        complex_types = [t for t in xsd_types if t["kind"] == "complexType" and t["elements"]]
        simple_types = [t for t in xsd_types if t["kind"] == "simpleType"]
        top_elements = [t for t in xsd_types if t["kind"] == "element" and t["elements"]]

        if complex_types or simple_types or top_elements:
            lines.append("## Types")
            lines.append("")

        for t in complex_types:
            lines.append(f"### {t['name']}")
            lines.append("")
            lines.append("| Element | Type | Min | Max |")
            lines.append("|---------|------|-----|-----|")
            for el in t["elements"]:
                lines.append(
                    f"| `{el['name']}` | `{el['type'] or '—'}` "
                    f"| {el['min'] or '—'} | {el['max'] or '—'} |"
                )
            lines.append("")

        for t in top_elements:
            lines.append(f"### {t['name']}")
            lines.append("")
            if t["type"]:
                lines.append(f"Type: `{t['type']}`")
                lines.append("")
            if t["elements"]:
                lines.append("| Element | Type | Min | Max |")
                lines.append("|---------|------|-----|-----|")
                for el in t["elements"]:
                    lines.append(
                        f"| `{el['name']}` | `{el['type'] or '—'}` "
                        f"| {el['min'] or '—'} | {el['max'] or '—'} |"
                    )
                lines.append("")

        for t in simple_types:
            lines.append(f"### {t['name']}")
            lines.append("")
            if t["base"]:
                lines.append(f"Base type: `{t['base']}`")
            if t["enums"]:
                lines.append(f"Values: {', '.join(f'`{e}`' for e in t['enums'])}")
            lines.append("")

    return "\n".join(lines)


def convert_wsdl(file_path: str) -> tuple[str, dict]:
    """Parse a WSDL file and produce structured Markdown.

    Returns (markdown_text, metadata).
    """
    t0 = time.perf_counter()
    filename = os.path.basename(file_path)

    logger.info("WSDL conversion started", extra={"file": filename})

    tree = ET.parse(file_path)
    root = tree.getroot()

    target_ns = root.get("targetNamespace", "")

    xsd_types = _parse_xsd_types(root)
    messages = _parse_messages(root)
    port_types = _parse_port_types(root)
    bindings = _parse_bindings(root)
    services = _parse_services(root)

    md_text = _to_markdown(
        target_ns, services, port_types, messages, bindings, xsd_types, filename,
    )

    total_ms = round((time.perf_counter() - t0) * 1000, 1)

    metadata: dict = {
        "total_ms": total_ms,
        "services": len(services),
        "port_types": len(port_types),
        "operations": sum(len(pt["operations"]) for pt in port_types),
        "messages": len(messages),
        "types": len(xsd_types),
        "bindings": len(bindings),
        "md_length": len(md_text),
    }

    logger.info("WSDL conversion completed", extra={
        "file": filename, "total_ms": total_ms,
        "operations": metadata["operations"],
        "types": metadata["types"],
    })

    return md_text, metadata
