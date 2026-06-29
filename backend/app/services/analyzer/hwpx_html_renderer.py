from __future__ import annotations

import html
import base64
import mimetypes
import zipfile
from pathlib import Path
from xml.etree import ElementTree


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _children(element: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return [child for child in list(element) if _local_name(child.tag) == name]


def _style_attr(style: dict[str, str]) -> str:
    if not style:
        return ""
    return f' style="{"; ".join(f"{key}: {html.escape(value)}" for key, value in style.items())}"'


def _safe_color(value: str | None) -> str:
    value = (value or "").strip()
    if not value or value.lower() == "none":
        return ""
    if not value.startswith("#"):
        value = f"#{value}"
    if len(value) == 9:
        # HWPX often stores colors as #AARRGGBB, while CSS expects #RRGGBB.
        value = f"#{value[3:]}"
    return value


def _parse_header_styles(archive: zipfile.ZipFile) -> dict[str, dict[str, dict[str, str]]]:
    try:
        header = ElementTree.fromstring(archive.read("Contents/header.xml"))
    except Exception:
        return {"border": {}, "char": {}, "para": {}}

    border_styles: dict[str, dict[str, str]] = {}
    char_styles: dict[str, dict[str, str]] = {}
    para_styles: dict[str, dict[str, str]] = {}

    for element in header.iter():
        name = _local_name(element.tag)
        element_id = element.attrib.get("id")
        if not element_id:
            continue
        if name == "borderFill":
            style: dict[str, str] = {}
            for child in element.iter():
                if _local_name(child.tag) == "winBrush":
                    face_color = _safe_color(child.attrib.get("faceColor"))
                    if face_color:
                        style["background-color"] = face_color
                    break
            border_styles[element_id] = style
        elif name == "charPr":
            style = {}
            text_color = _safe_color(element.attrib.get("textColor"))
            if text_color and text_color != "#000000":
                style["color"] = text_color
            height = element.attrib.get("height")
            if height and height.isdigit():
                # HWP height is roughly 1/100 pt. Keep it bounded for browser readability.
                font_size = max(10, min(28, int(height) / 100))
                if abs(font_size - 10) > 0.1:
                    style["font-size"] = f"{font_size:.1f}pt"
            if any(_local_name(child.tag) == "bold" for child in list(element)):
                style["font-weight"] = "700"
            char_styles[element_id] = style
        elif name == "paraPr":
            style = {}
            align = next((child for child in list(element) if _local_name(child.tag) == "align"), None)
            horizontal = (align.attrib.get("horizontal") if align is not None else "").upper()
            align_map = {
                "LEFT": "left",
                "RIGHT": "right",
                "CENTER": "center",
                "JUSTIFY": "justify",
                "DISTRIBUTE": "justify",
            }
            if horizontal in align_map:
                style["text-align"] = align_map[horizontal]
            para_styles[element_id] = style

    return {"border": border_styles, "char": char_styles, "para": para_styles}


def _image_data_uris(archive: zipfile.ZipFile) -> dict[str, str]:
    images: dict[str, str] = {}
    for name in archive.namelist():
        if not name.lower().startswith("bindata/"):
            continue
        file_name = Path(name).name
        image_id = Path(file_name).stem
        content_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        try:
            encoded = base64.b64encode(archive.read(name)).decode("ascii")
        except Exception:
            continue
        images[image_id] = f"data:{content_type};base64,{encoded}"
    return images


def _text_excluding_tables(element: ElementTree.Element) -> str:
    parts: list[str] = []

    def walk(node: ElementTree.Element) -> None:
        if _local_name(node.tag) in {"tbl", "pic"}:
            return
        if node.text and node.text.strip():
            parts.append(node.text.strip())
        for child in list(node):
            walk(child)
            if child.tail and child.tail.strip():
                parts.append(child.tail.strip())

    walk(element)
    return " ".join(parts).strip()


def _run_text(run: ElementTree.Element) -> str:
    parts: list[str] = []
    def walk(node: ElementTree.Element) -> None:
        if _local_name(node.tag) == "tbl":
            return
        if node.text and node.text.strip():
            parts.append(node.text.strip())
        for child in list(node):
            walk(child)
            if child.tail and child.tail.strip():
                parts.append(child.tail.strip())

    walk(run)
    return " ".join(parts).strip()


def _render_run(run: ElementTree.Element, styles: dict[str, dict[str, dict[str, str]]]) -> str:
    text = _run_text(run)
    parts = []
    if text:
        char_style = styles["char"].get(run.attrib.get("charPrIDRef", ""), {})
        parts.append(f"<span{_style_attr(char_style)}>{html.escape(text)}</span>")
    for child in list(run):
        name = _local_name(child.tag)
        if name == "tbl":
            parts.append(_render_table(child, styles))
        elif name == "pic":
            parts.append(_render_picture(child, styles))
    return "".join(parts)


def _render_paragraph(paragraph: ElementTree.Element, styles: dict[str, dict[str, dict[str, str]]]) -> str:
    parts = []
    for child in list(paragraph):
        name = _local_name(child.tag)
        if name == "run":
            parts.append(_render_run(child, styles))
        elif name == "tbl":
            parts.append(_render_table(child, styles))
        elif name == "pic":
            parts.append(_render_picture(child, styles))

    if not "".join(parts).strip():
        return ""
    para_style = styles["para"].get(paragraph.attrib.get("paraPrIDRef", ""), {})
    return f"<p{_style_attr(para_style)}>{''.join(parts)}</p>"


def _render_cell_content(cell: ElementTree.Element, styles: dict[str, dict[str, dict[str, str]]]) -> str:
    parts: list[str] = []
    for sub_list in _children(cell, "subList"):
        for child in list(sub_list):
            name = _local_name(child.tag)
            if name == "p":
                rendered = _render_paragraph(child, styles)
            elif name == "tbl":
                rendered = _render_table(child, styles)
            else:
                rendered = ""
            if rendered:
                parts.append(rendered)
    if parts:
        return "".join(parts)
    fallback = _text_excluding_tables(cell)
    return f"<div>{html.escape(fallback)}</div>" if fallback else "&nbsp;"


def _cell_style(cell: ElementTree.Element, styles: dict[str, dict[str, dict[str, str]]]) -> dict[str, str]:
    style = dict(styles["border"].get(cell.attrib.get("borderFillIDRef", ""), {}))
    sub_list = next((child for child in list(cell) if _local_name(child.tag) == "subList"), None)
    vertical_align = (sub_list.attrib.get("vertAlign") if sub_list is not None else "").upper()
    vertical_map = {
        "TOP": "top",
        "CENTER": "middle",
        "BOTTOM": "bottom",
    }
    if vertical_align in vertical_map:
        style["vertical-align"] = vertical_map[vertical_align]
    return style


def _hwpx_size_to_px(value: str | None) -> int | None:
    if not value:
        return None
    try:
        number = abs(int(value))
    except ValueError:
        return None
    # HWPX dimensions are not CSS pixels. /100 gives readable browser-scale output
    # for the files collected from G2B without needing full page-layout math.
    return max(1, min(1200, round(number / 100)))


def _render_picture(picture: ElementTree.Element, styles: dict[str, dict[str, dict[str, str]]]) -> str:
    image = next((child for child in picture.iter() if _local_name(child.tag) == "img"), None)
    image_id = image.attrib.get("binaryItemIDRef") if image is not None else ""
    src = styles.get("image", {}).get(image_id or "")
    if not src:
        return ""

    size = next((child for child in picture.iter() if _local_name(child.tag) == "curSz"), None)
    width = _hwpx_size_to_px(size.attrib.get("width") if size is not None else None)
    height = _hwpx_size_to_px(size.attrib.get("height") if size is not None else None)
    image_style = {
        "max-width": "100%",
        "height": "auto",
    }
    if width:
        image_style["width"] = f"{width}px"
    if height and not width:
        image_style["height"] = f"{height}px"
    style = _style_attr(image_style)
    return f'<figure class="hwpx-image"><img src="{html.escape(src)}"{style} alt="" /></figure>'


def _render_table(table: ElementTree.Element, styles: dict[str, dict[str, dict[str, str]]]) -> str:
    rows = _children(table, "tr")
    if not rows:
        return ""

    rendered_rows: list[str] = []
    for row in rows:
        cells = _children(row, "tc")
        rendered_cells: list[str] = []
        for cell in cells:
            span = next((child for child in list(cell) if _local_name(child.tag) == "cellSpan"), None)
            colspan = span.attrib.get("colSpan", "1") if span is not None else "1"
            rowspan = span.attrib.get("rowSpan", "1") if span is not None else "1"
            attrs = []
            if colspan and colspan != "1":
                attrs.append(f'colspan="{html.escape(colspan)}"')
            if rowspan and rowspan != "1":
                attrs.append(f'rowspan="{html.escape(rowspan)}"')

            style = _style_attr(_cell_style(cell, styles))
            content = _render_cell_content(cell, styles)
            rendered_cells.append(f"<td {' '.join(attrs)}{style}>{content}</td>")
        rendered_rows.append(f"<tr>{''.join(rendered_cells)}</tr>")

    return f"<table>{''.join(rendered_rows)}</table>"


def _render_section(section_xml: bytes, styles: dict[str, dict[str, dict[str, str]]]) -> str:
    root = ElementTree.fromstring(section_xml)
    blocks: list[str] = []
    for child in list(root):
        name = _local_name(child.tag)
        if name == "p":
            rendered = _render_paragraph(child, styles)
        elif name == "tbl":
            rendered = _render_table(child, styles)
        else:
            rendered = ""
        if rendered:
            blocks.append(rendered)
    return "\n".join(blocks)


def hwpx_to_html_viewer(file_path: Path) -> tuple[Path | None, str]:
    output_dir = file_path.parent / "converted"
    output_dir.mkdir(parents=True, exist_ok=True)
    html_path = output_dir / f"{file_path.stem}.viewer.html"

    try:
        with zipfile.ZipFile(file_path) as archive:
            styles = _parse_header_styles(archive)
            styles["image"] = _image_data_uris(archive)
            section_names = sorted(
                name
                for name in archive.namelist()
                if name.lower().startswith("contents/section") and name.lower().endswith(".xml")
            )
            if not section_names:
                return None, "HWPX 본문 XML을 찾지 못했습니다."
            body = "\n".join(_render_section(archive.read(name), styles) for name in section_names)
    except zipfile.BadZipFile:
        return None, "HWPX 파일 구조가 올바른 ZIP 형식이 아닙니다."
    except Exception as exc:
        return None, f"HWPX HTML 뷰어 생성 실패: {exc}"

    if not body.strip():
        return None, "HWPX HTML 뷰어에 표시할 본문을 찾지 못했습니다."

    html_doc = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(file_path.name)}</title>
  <style>
    body {{
      margin: 0;
      background: #eef2f7;
      color: #172033;
      font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", Arial, sans-serif;
      line-height: 1.65;
    }}
    main {{
      box-sizing: border-box;
      max-width: 980px;
      min-height: 100vh;
      margin: 0 auto;
      padding: 42px 52px;
      background: #fff;
      box-shadow: 0 16px 40px rgba(18, 35, 66, 0.12);
    }}
    h1 {{
      margin: 0 0 24px;
      font-size: 20px;
      line-height: 1.35;
    }}
    p {{
      margin: 0 0 12px;
      white-space: pre-wrap;
    }}
    span {{
      white-space: pre-wrap;
    }}
    .hwpx-image {{
      margin: 10px 0 16px;
      text-align: center;
    }}
    .hwpx-image img {{
      display: inline-block;
      object-fit: contain;
      vertical-align: middle;
    }}
    table {{
      width: 100%;
      margin: 14px 0 22px;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 13px;
    }}
    td, th {{
      border: 1px solid #8d98aa;
      padding: 8px 10px;
      vertical-align: top;
      word-break: keep-all;
      overflow-wrap: anywhere;
    }}
    td p {{
      margin: 0;
    }}
    td p + p {{
      margin-top: 6px;
    }}
    td div + div {{
      margin-top: 6px;
    }}
    table table {{
      margin: 8px 0;
      font-size: 12px;
    }}
  </style>
</head>
<body>
  <main>
    <h1>{html.escape(file_path.name)}</h1>
    {body}
  </main>
</body>
</html>
"""
    html_path.write_text(html_doc, encoding="utf-8")
    return html_path, ""
