#!/usr/bin/env python3
"""Generate a brace-style mind map image from JSON data.

Usage:
    python3 mindmap_generator.py
    python3 mindmap_generator.py --input example_mindmap.json --output demo.png
    python3 mindmap_generator.py --format svg --output demo.svg

The JSON structure must look like:
{
  "title": "Root",
  "children": [
    {
      "title": "Child A",
      "children": [
        {"title": "Grandchild A1"}
      ]
    }
  ]
}
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any


MAX_LEVELS = 5
HORIZONTAL_PADDING = 18
VERTICAL_PADDING = 12
CHAR_WIDTH = 14
LINE_HEIGHT = 22
BOX_RX = 14
SIBLING_GAP = 24
LEVEL_GAP = 110
BRACE_GAP = 28
BRACE_WIDTH = 18
MARGIN_X = 60
MARGIN_Y = 50

LEVEL_STYLES = {
    1: {"fill": "#DCEBFF", "stroke": "#3B82F6", "text": "#0F172A"},
    2: {"fill": "#E8FFF2", "stroke": "#22C55E", "text": "#0F172A"},
    3: {"fill": "#FFF5D6", "stroke": "#F59E0B", "text": "#0F172A"},
    4: {"fill": "#FFE6E6", "stroke": "#EF4444", "text": "#0F172A"},
    5: {"fill": "#F2E8FF", "stroke": "#8B5CF6", "text": "#0F172A"},
}


@dataclass
class Node:
    title: str
    children: list["Node"] = field(default_factory=list)
    level: int = 1
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    subtree_height: float = 0.0


def parse_args() -> argparse.Namespace:
    app_dir = get_app_dir()
    default_input = app_dir / "example_mindmap.json"
    default_output = app_dir / "example_mindmap.png"

    parser = argparse.ArgumentParser(description="Generate a brace-style mind map from JSON.")
    parser.add_argument(
        "--input",
        default=str(default_input),
        help="Path to the input JSON file.",
    )
    parser.add_argument(
        "--output",
        default=str(default_output),
        help="Path to the output file.",
    )
    parser.add_argument(
        "--format",
        choices=["png", "svg"],
        default="png",
        help="Output format. png requires Pillow when running as .py.",
    )
    parser.add_argument(
        "--title",
        default="思维导图",
        help="Document title shown in the SVG metadata.",
    )
    return parser.parse_args()


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def is_double_click_mode() -> bool:
    return len(sys.argv) == 1


def show_message(title: str, message: str, is_error: bool = False) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        if is_error:
            messagebox.showerror(title, message)
        else:
            messagebox.showinfo(title, message)
        root.destroy()
    except Exception:
        stream = sys.stderr if is_error else sys.stdout
        print(f"{title}: {message}", file=stream)


def open_output_file(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            import subprocess

            subprocess.Popen(["open", str(path)])
        else:
            import subprocess

            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"未找到输入文件: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"JSON 格式错误: {exc}") from exc


def build_tree(data: dict[str, Any], level: int = 1) -> Node:
    if level > MAX_LEVELS:
        raise SystemExit(f"层级超过限制：最多支持 {MAX_LEVELS} 级。")

    title = str(data.get("title", "")).strip()
    if not title:
        raise SystemExit("每个节点都必须包含非空的 title 字段。")

    raw_children = data.get("children", [])
    if raw_children is None:
        raw_children = []
    if not isinstance(raw_children, list):
        raise SystemExit(f"节点 '{title}' 的 children 必须是数组。")

    node = Node(title=title, level=level)
    node.children = [build_tree(child, level + 1) for child in raw_children]
    return node


def split_text(text: str, max_chars: int = 12) -> list[str]:
    text = text.strip()
    if not text:
        return [""]

    lines: list[str] = []
    current = ""
    for char in text:
        current += char
        if len(current) >= max_chars:
            lines.append(current)
            current = ""
    if current:
        lines.append(current)
    return lines


def measure_text(text: str) -> tuple[float, float, list[str]]:
    lines = split_text(text)
    max_len = max(len(line) for line in lines) if lines else 1
    width = max(110, max_len * CHAR_WIDTH + HORIZONTAL_PADDING * 2)
    height = len(lines) * LINE_HEIGHT + VERTICAL_PADDING * 2
    return width, height, lines


def compute_sizes(node: Node) -> None:
    width, height, _ = measure_text(node.title)
    node.width = width
    node.height = height

    if not node.children:
        node.subtree_height = height
        return

    for child in node.children:
        compute_sizes(child)

    children_height = sum(child.subtree_height for child in node.children)
    children_height += SIBLING_GAP * (len(node.children) - 1)
    node.subtree_height = max(height, children_height)


def position_tree(node: Node, left: float, top: float) -> None:
    node.x = left
    node.y = top + (node.subtree_height - node.height) / 2

    if not node.children:
        return

    children_total = sum(child.subtree_height for child in node.children)
    children_total += SIBLING_GAP * (len(node.children) - 1)
    cursor_y = top + (node.subtree_height - children_total) / 2

    next_left = left + node.width + LEVEL_GAP
    for child in node.children:
        position_tree(child, next_left, cursor_y)
        cursor_y += child.subtree_height + SIBLING_GAP


def iter_nodes(node: Node) -> list[Node]:
    result = [node]
    for child in node.children:
        result.extend(iter_nodes(child))
    return result


def get_canvas_size(root: Node) -> tuple[int, int]:
    nodes = iter_nodes(root)
    max_x = max(node.x + node.width for node in nodes)
    max_y = max(node.y + node.height for node in nodes)
    width = int(math.ceil(max_x + MARGIN_X))
    height = int(math.ceil(max_y + MARGIN_Y))
    return width, height

def brace_path(x: float, y1: float, y2: float, w: float = BRACE_WIDTH) -> str:
    if y2 < y1:
        y1, y2 = y2, y1
    h = y2 - y1
    if h < 24:
        return f"M {x:.1f} {y1:.1f} L {x:.1f} {y2:.1f}"

    mid = (y1 + y2) / 2
    a = h * 0.18
    b = h * 0.10

    return (
        f"M {x:.1f} {y1:.1f} "
        f"C {x + w:.1f} {y1:.1f} {x + w:.1f} {y1 + a:.1f} {x:.1f} {y1 + a:.1f} "
        f"C {x - w:.1f} {y1 + a + b:.1f} {x - w:.1f} {mid - b:.1f} {x:.1f} {mid:.1f} "
        f"C {x - w:.1f} {mid + b:.1f} {x - w:.1f} {y2 - a - b:.1f} {x:.1f} {y2 - a:.1f} "
        f"C {x + w:.1f} {y2 - a:.1f} {x + w:.1f} {y2:.1f} {x:.1f} {y2:.1f}"
    )


def render_text(node: Node) -> str:
    _, _, lines = measure_text(node.title)
    text_x = node.x + node.width / 2
    content_height = len(lines) * LINE_HEIGHT
    start_y = node.y + (node.height - content_height) / 2 + LINE_HEIGHT * 0.82

    parts = [
        (
            f'<text x="{text_x:.1f}" y="{start_y + index * LINE_HEIGHT:.1f}" '
            f'text-anchor="middle" font-size="18" font-family="Microsoft YaHei, '
            f'SimHei, Arial, sans-serif" fill="{LEVEL_STYLES[node.level]["text"]}">'
            f"{escape(line)}</text>"
        )
        for index, line in enumerate(lines)
    ]
    return "\n".join(parts)


def render_edges(node: Node) -> str:
    parts: list[str] = []
    stroke = LEVEL_STYLES[node.level]["stroke"]

    if node.children:
        parent_x = node.x + node.width
        parent_y = node.y + node.height / 2

        child_centers = [(c.x, c.y + c.height / 2) for c in node.children]
        ys = [y for _, y in child_centers]
        min_y = min(ys)
        max_y = max(ys)

        if len(node.children) == 1:
            child = node.children[0]
            x2 = child.x
            y2 = child.y + child.height / 2
            parts.append(
                f'<path d="M {parent_x:.1f} {parent_y:.1f} L {x2:.1f} {y2:.1f}" '
                f'fill="none" stroke="{stroke}" stroke-width="2.5" />'
            )
        else:
            bx = parent_x + BRACE_GAP
            parts.append(
                f'<path d="M {parent_x:.1f} {parent_y:.1f} L {bx:.1f} {parent_y:.1f}" '
                f'fill="none" stroke="{stroke}" stroke-width="2.5" />'
            )
            parts.append(
                f'<path d="{brace_path(bx, min_y, max_y)}" fill="none" '
                f'stroke="{stroke}" stroke-width="2.5" />'
            )
            for child in node.children:
                cy = child.y + child.height / 2
                parts.append(
                    f'<path d="M {bx:.1f} {cy:.1f} L {child.x:.1f} {cy:.1f}" '
                    f'fill="none" stroke="{stroke}" stroke-width="2.5" />'
                )

        for child in node.children:
            parts.append(render_edges(child))

    return "\n".join(part for part in parts if part)


def render_nodes(root: Node) -> str:
    parts: list[str] = []
    for node in iter_nodes(root):
        style = LEVEL_STYLES[node.level]
        parts.append(
            f'<rect x="{node.x:.1f}" y="{node.y:.1f}" width="{node.width:.1f}" '
            f'height="{node.height:.1f}" rx="{BOX_RX}" ry="{BOX_RX}" '
            f'fill="{style["fill"]}" stroke="{style["stroke"]}" stroke-width="2.2" />'
        )
        parts.append(render_text(node))
    return "\n".join(parts)


def render_svg(root: Node, doc_title: str) -> str:
    width, height = get_canvas_size(root)
    background = "#F8FAFC"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <title>{escape(doc_title)}</title>
  <rect width="100%" height="100%" fill="{background}" />
  {render_edges(root)}
  {render_nodes(root)}
</svg>
"""

def cubic_bezier_points(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int = 24,
) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for i in range(steps + 1):
        t = i / steps
        mt = 1 - t
        x = (
            mt**3 * p0[0]
            + 3 * mt**2 * t * p1[0]
            + 3 * mt * t**2 * p2[0]
            + t**3 * p3[0]
        )
        y = (
            mt**3 * p0[1]
            + 3 * mt**2 * t * p1[1]
            + 3 * mt * t**2 * p2[1]
            + t**3 * p3[1]
        )
        points.append((x, y))
    return points


def brace_points(x: float, y1: float, y2: float, w: float = BRACE_WIDTH) -> list[tuple[float, float]]:
    if y2 < y1:
        y1, y2 = y2, y1
    h = y2 - y1
    if h < 24:
        return [(x, y1), (x, y2)]

    mid = (y1 + y2) / 2
    a = h * 0.18
    b = h * 0.10

    segments = [
        ((x, y1), (x + w, y1), (x + w, y1 + a), (x, y1 + a)),
        ((x, y1 + a), (x - w, y1 + a + b), (x - w, mid - b), (x, mid)),
        ((x, mid), (x - w, mid + b), (x - w, y2 - a - b), (x, y2 - a)),
        ((x, y2 - a), (x + w, y2 - a), (x + w, y2), (x, y2)),
    ]

    points: list[tuple[float, float]] = []
    for index, seg in enumerate(segments):
        seg_points = cubic_bezier_points(*seg)
        if index > 0:
            seg_points = seg_points[1:]
        points.extend(seg_points)
    return points


def find_font_path() -> str | None:
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/msyhbd.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKSC-Regular.otf",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def load_font(size: int):
    try:
        from PIL import ImageFont
    except Exception as exc:
        raise SystemExit(
            "当前运行环境缺少 Pillow，无法输出 PNG。\n"
            "解决办法：\n"
            "1) 安装依赖：pip install pillow\n"
            "2) 或改用输出 SVG：--format svg --output xxx.svg"
        ) from exc

    font_path = find_font_path()
    if font_path:
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def export_png(root: Node, output_path: Path) -> None:
    try:
        from PIL import Image, ImageDraw
    except Exception as exc:
        raise SystemExit(
            "当前运行环境缺少 Pillow，无法输出 PNG。\n"
            "解决办法：\n"
            "1) 安装依赖：pip install pillow\n"
            "2) 或改用输出 SVG：--format svg --output xxx.svg"
        ) from exc

    width, height = get_canvas_size(root)
    image = Image.new("RGB", (width, height), "#F8FAFC")
    draw = ImageDraw.Draw(image)
    font = load_font(18)

    for node in iter_nodes(root):
        stroke = LEVEL_STYLES[node.level]["stroke"]
        if not node.children:
            continue

        parent_x = node.x + node.width
        parent_y = node.y + node.height / 2
        if len(node.children) == 1:
            child = node.children[0]
            draw.line(
                [(parent_x, parent_y), (child.x, child.y + child.height / 2)],
                fill=stroke,
                width=3,
            )
        else:
            bx = parent_x + BRACE_GAP
            draw.line([(parent_x, parent_y), (bx, parent_y)], fill=stroke, width=3)
            ys = [child.y + child.height / 2 for child in node.children]
            draw.line(brace_points(bx, min(ys), max(ys)), fill=stroke, width=3)
            for child in node.children:
                cy = child.y + child.height / 2
                draw.line([(bx, cy), (child.x, cy)], fill=stroke, width=3)

    for node in iter_nodes(root):
        style = LEVEL_STYLES[node.level]
        draw.rounded_rectangle(
            [node.x, node.y, node.x + node.width, node.y + node.height],
            radius=BOX_RX,
            fill=style["fill"],
            outline=style["stroke"],
            width=2,
        )

        _, _, lines = measure_text(node.title)
        content_height = len(lines) * LINE_HEIGHT
        start_y = node.y + (node.height - content_height) / 2
        for index, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            text_x = node.x + (node.width - text_w) / 2
            text_y = start_y + index * LINE_HEIGHT + (LINE_HEIGHT - text_h) / 2 - 1
            draw.text((text_x, text_y), line, font=font, fill=style["text"])

    image.save(output_path, format="PNG")


def main() -> None:
    auto_mode = is_double_click_mode()
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()

    try:
        data = load_json(input_path)
        root = build_tree(data)
        compute_sizes(root)
        position_tree(root, MARGIN_X, MARGIN_Y)
        svg = render_svg(root, args.title)

        if args.format == "svg" and output_path.suffix.lower() != ".svg":
            output_path = output_path.with_suffix(".svg")
        if args.format == "png" and output_path.suffix.lower() != ".png":
            output_path = output_path.with_suffix(".png")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if args.format == "svg":
            output_path.write_text(svg, encoding="utf-8")
        else:
            export_png(root, output_path)

        print(f"思维导图已生成: {output_path}")

        if auto_mode:
            open_output_file(output_path)
            show_message("生成成功", f"思维导图已生成：\n{output_path}")
    except SystemExit as exc:
        message = str(exc)
        if auto_mode:
            show_message("生成失败", message, is_error=True)
            return
        raise


if __name__ == "__main__":
    main()
