from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from xml.parsers import expat


SVG_NAMESPACE = "http://www.w3.org/2000/svg"
MAX_SVG_BYTES = 4 * 1024 * 1024
MAX_SVG_DEPTH = 128
MAX_SVG_NODES = 100_000
MAX_SVG_DIMENSION = 8192
MAX_SVG_AREA = 64_000_000

_SVG_ELEMENTS = {
    "svg", "g", "defs", "path", "rect", "circle", "ellipse", "line",
    "polyline", "polygon", "text", "tspan", "title", "desc", "metadata",
    "style", "clipPath", "mask", "pattern", "linearGradient", "radialGradient",
    "stop", "use", "symbol", "marker", "filter", "feBlend", "feColorMatrix",
    "feComponentTransfer", "feComposite", "feConvolveMatrix", "feDiffuseLighting",
    "feDisplacementMap", "feDistantLight", "feDropShadow", "feFlood", "feFuncA",
    "feFuncB", "feFuncG", "feFuncR", "feGaussianBlur", "feMerge", "feMergeNode",
    "feMorphology", "feOffset", "fePointLight", "feSpecularLighting", "feSpotLight",
    "feTile", "feTurbulence",
}
_LOCAL_URL_RE = re.compile(r"url\s*\(\s*['\"]?#[-a-z0-9_.:]+['\"]?\s*\)", re.I)
_ALLOWED_ATTRIBUTE_NAMESPACES = {
    "http://www.w3.org/1999/xlink",
    "http://www.w3.org/XML/1998/namespace",
}


def _reject_xml_feature(*_args: object) -> None:
    raise ValueError("unsupported XML feature in SVG")


def _split_tag(tag: str) -> tuple[str, str]:
    if tag.startswith("{") and "}" in tag:
        namespace, local = tag[1:].split("}", 1)
        return namespace, local
    return "", tag


def _safe_style(value: str) -> bool:
    if "\\" in value or "@" in value:
        return False
    lowered = _LOCAL_URL_RE.sub("", value.lower())
    return all(token not in lowered for token in (
        "url", "expression(", "javascript:", "data:", "http:", "https:", "file:", "blob:",
    ))


def _svg_length(value: str) -> float:
    text = str(value or "").strip().lower()
    for suffix in ("px", "pt", "mm", "cm"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break
    try:
        return float(text)
    except ValueError:
        return 0.0


def _root_dimensions(attrs: dict[str, str]) -> tuple[float, float]:
    width = _svg_length(next((value for key, value in attrs.items() if key.lower() == "width"), ""))
    height = _svg_length(next((value for key, value in attrs.items() if key.lower() == "height"), ""))
    viewbox = next((value for key, value in attrs.items() if key.lower() == "viewbox"), "")
    values: list[float] = []
    if viewbox:
        try:
            values = [float(item) for item in re.split(r"[\s,]+", viewbox.strip()) if item]
        except ValueError:
            values = []
    if width <= 0 and len(values) == 4:
        width = values[2]
    if height <= 0 and len(values) == 4:
        height = values[3]
    return width, height


def svg_dimensions(data: bytes) -> tuple[int, int] | None:
    """Validate a bounded static SVG and return its intrinsic dimensions."""
    if not isinstance(data, (bytes, bytearray)) or not data or len(data) > MAX_SVG_BYTES:
        return None
    # Run an encoding-aware XML pass before ElementTree. This rejects DTDs,
    # entity declarations, and processing instructions even when the payload
    # uses UTF-16 or another encoding that cannot be found by byte searching.
    try:
        security_parser = expat.ParserCreate()
        security_parser.StartDoctypeDeclHandler = _reject_xml_feature
        security_parser.EntityDeclHandler = _reject_xml_feature
        security_parser.ExternalEntityRefHandler = _reject_xml_feature
        security_parser.ProcessingInstructionHandler = _reject_xml_feature
        security_parser.Parse(bytes(data), True)
    except (expat.ExpatError, ValueError, TypeError):
        return None

    parser = ET.XMLPullParser(events=("start", "end"))
    try:
        parser.feed(bytes(data))
        parser.close()
    except (ET.ParseError, ValueError, TypeError):
        return None

    depth = 0
    nodes = 0
    root_seen = False
    root_closed = False
    width = height = 0.0
    style_depth = 0
    try:
        for event, element in parser.read_events():
            namespace, name = _split_tag(str(element.tag))
            if event == "start":
                if style_depth or root_closed:
                    return None
                depth += 1
                nodes += 1
                if depth > MAX_SVG_DEPTH or nodes > MAX_SVG_NODES:
                    return None
                if namespace not in {"", SVG_NAMESPACE} or name not in _SVG_ELEMENTS:
                    return None
                if not root_seen:
                    if name != "svg":
                        return None
                    root_seen = True
                    width, height = _root_dimensions({str(key): str(value) for key, value in element.attrib.items()})
                for raw_key, raw_value in element.attrib.items():
                    attr_namespace, attr_name = _split_tag(str(raw_key))
                    key = attr_name.lower()
                    value = str(raw_value)
                    if attr_namespace and attr_namespace not in _ALLOWED_ATTRIBUTE_NAMESPACES:
                        return None
                    if key.startswith("on") or key in {"src", "base"} or not _safe_style(value):
                        return None
                    if key == "href" and not value.strip().startswith("#"):
                        return None
                if name == "style":
                    style_depth = depth
            else:
                if name == "style":
                    if style_depth != depth or not _safe_style("".join(element.itertext())):
                        return None
                    style_depth = 0
                depth -= 1
                if depth == 0:
                    root_closed = True
                element.clear()
    except (RuntimeError, ValueError, TypeError):
        return None

    if (
        not root_seen
        or not root_closed
        or depth != 0
        or not math.isfinite(width)
        or not math.isfinite(height)
        or width <= 0
        or height <= 0
        or width > MAX_SVG_DIMENSION
        or height > MAX_SVG_DIMENSION
        or width * height > MAX_SVG_AREA
    ):
        return None
    return int(width + 0.999999), int(height + 0.999999)
