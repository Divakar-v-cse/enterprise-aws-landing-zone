#!/usr/bin/env python3
"""Render captured terminal output into PNG evidence images.

Screenshots in a portfolio repository have to be *real*. This script does not
fake a terminal: it takes a transcript that was actually captured from a real
command run (``screenshots/*.txt``) and renders it faithfully as a PNG, with the
capture header preserved.

Every generated image carries a footer stating the source transcript, so an
image can always be traced back to the text it came from.

Usage
-----
    python scripts/make_evidence_images.py --all
    python scripts/make_evidence_images.py \
        --input screenshots/terraform-plan.txt \
        --title "terraform plan - dev (zero-cost mode)"

Requires Pillow (``pip install pillow``).

Exit codes
----------
    0  images written
    1  Pillow missing, input missing, or nothing to render
"""

from __future__ import annotations

import argparse
import logging
import sys
import textwrap
from pathlib import Path

LOG = logging.getLogger("evidence")

FONT_CANDIDATES = (
    r"C:\Windows\Fonts\consola.ttf",
    r"C:\Windows\Fonts\lucon.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/dejavu/DejaVuSansMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
)

BACKGROUND = (13, 17, 23)
FOREGROUND = (201, 209, 217)
ACCENT = (88, 166, 255)
MUTED = (110, 118, 129)
HEADER_BG = (22, 27, 34)
SUCCESS = (63, 185, 80)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="make_evidence_images",
        description="Render real command transcripts (*.txt) as PNG evidence images.",
    )
    parser.add_argument("--input", help="Transcript file to render.")
    parser.add_argument("--output", help="Output PNG path (default: same stem as input).")
    parser.add_argument("--title", default=None, help="Header title (default: derived from filename).")
    parser.add_argument("--all", action="store_true", help="Render every screenshots/*.txt transcript.")
    parser.add_argument("--dir", default="screenshots", help="Transcript directory (default: screenshots).")
    parser.add_argument("--font-size", type=int, default=14)
    parser.add_argument("--max-width", type=int, default=1500)
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def load_font(size: int):
    from PIL import ImageFont

    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:  # pragma: no cover - platform specific
                continue
    LOG.warning("No monospace TTF found; falling back to the PIL bitmap font.")
    return ImageFont.load_default()


def colourise(line: str) -> tuple[int, int, int]:
    lowered = line.lower()
    if line.startswith(("ERROR", "FAIL", "[FAIL", "RESULT: FAIL")) or " error:" in lowered:
        return (248, 81, 73)
    if line.startswith(("WARN", "[WARN", "warning:")) or " warning" in lowered:
        return (210, 153, 34)
    if "PASS" in line or line.startswith(("Success", "Plan:", "✓")):
        return SUCCESS
    if line.startswith(("$", "PS>", ">", "#")):
        return ACCENT
    return FOREGROUND


def render_transcript(
    text: str, title: str, font, max_width: int, font_size: int
) -> list:
    """Render a transcript into one or more images (paginated by height)."""
    from PIL import Image, ImageDraw

    line_height = int(font_size * 1.55)
    padding = 24
    header_height = 54
    footer_height = 34
    max_page_height = 2400

    char_width = max(font.getlength("M"), 6)
    usable = max_width - padding * 2
    columns = max(int(usable / char_width), 60)

    wrapped: list[str] = []
    for raw in text.replace("\t", "    ").splitlines():
        if not raw:
            wrapped.append("")
            continue
        # Hard-wrap long lines so nothing is lost off the right edge.
        for chunk in textwrap.wrap(raw, width=columns, replace_whitespace=False, drop_whitespace=False) or [""]:
            wrapped.append(chunk)

    lines_per_page = (max_page_height - header_height - footer_height - padding * 2) // line_height
    pages = [wrapped[i : i + lines_per_page] for i in range(0, len(wrapped), lines_per_page)] or [[""]]

    images = []
    for page_index, page_lines in enumerate(pages, start=1):
        height = header_height + footer_height + padding * 2 + line_height * len(page_lines)
        image = Image.new("RGB", (max_width, height), BACKGROUND)
        draw = ImageDraw.Draw(image)

        # Header bar
        draw.rectangle([0, 0, max_width, header_height], fill=HEADER_BG)
        draw.text((padding, 14), title, font=font, fill=ACCENT)
        suffix = f"   (page {page_index}/{len(pages)})" if len(pages) > 1 else ""
        draw.text(
            (max_width - padding, 16),
            f"real captured output{suffix}",
            font=font,
            fill=MUTED,
            anchor="ra",
        )

        y = header_height + padding
        for line in page_lines:
            draw.text((padding, y), line, font=font, fill=colourise(line))
            y += line_height

        footer = f"source: {title}"
        draw.line([(0, height - footer_height), (max_width, height - footer_height)], fill=(48, 54, 61))
        draw.text((padding, height - footer_height + 9), footer, font=font, fill=MUTED)

        images.append(image)
    return images


def render_file(path: Path, output: Path, title: str | None, font_size: int, max_width: int) -> list[Path]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise ValueError(f"{path} is empty - capture the command output first.")

    font = load_font(font_size)
    heading = title or path.stem.replace("-", " ").replace("_", " ").title()
    images = render_transcript(text, heading, font, max_width, font_size)

    output.parent.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for index, image in enumerate(images, start=1):
        if len(images) == 1:
            target = output
        else:
            target = output.with_name(f"{output.stem}-{index}{output.suffix}")
        image.save(target, "PNG", optimize=True)
        written.append(target)
        LOG.info("Wrote %s (%dx%d)", target, image.width, image.height)
    return written


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )

    try:
        import PIL  # noqa: F401
    except ImportError:
        LOG.error("Pillow is required: python -m pip install pillow")
        return 1

    if not args.all and not args.input:
        LOG.error("Provide --input <transcript.txt> or --all.")
        return 1

    if args.all:
        directory = Path(args.dir)
        transcripts = sorted(directory.glob("*.txt"))
        if not transcripts:
            LOG.error("No transcripts found in %s. Capture evidence first.", directory)
            return 1
        targets = [(path, path.with_suffix(".png"), None) for path in transcripts]
    else:
        source = Path(args.input)
        if not source.is_file():
            LOG.error("Transcript not found: %s", source)
            return 1
        destination = Path(args.output) if args.output else source.with_suffix(".png")
        targets = [(source, destination, args.title)]

    failures = 0
    for source, destination, title in targets:
        try:
            render_file(source, destination, title, args.font_size, args.max_width)
        except (ValueError, OSError) as exc:
            LOG.error("%s", exc)
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
