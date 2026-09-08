"""One-off generator for the canonical fixture's synthetic screenshots.

Not part of the app's runtime dependencies — run manually (after
`pip install pillow`) only if the fixtures under backend/fixtures/acme/
need to be regenerated.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "acme"

WHITE = (255, 255, 255)
BLACK = (20, 20, 30)
GRAY = (120, 124, 138)
BORDER = (180, 186, 205)
HEADER_BG = (30, 39, 97)


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", size)
    except OSError:
        return ImageFont.load_default()


def _draw_field(draw, x, y, label, value, width=420, required=False):
    label_font = _font(14)
    value_font = _font(16)
    label_text = label + (" *" if required else "")
    draw.text((x, y), label_text, fill=GRAY, font=label_font)
    box_top = y + 20
    draw.rectangle([x, box_top, x + width, box_top + 34], outline=BORDER, width=2, fill=WHITE)
    draw.text((x + 10, box_top + 8), value, fill=BLACK, font=value_font)
    return box_top + 34 + 26


def make_intake_form():
    img = Image.new("RGB", (520, 480), WHITE)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 520, 50], fill=HEADER_BG)
    draw.text((16, 14), "Case Intake Form", fill=WHITE, font=_font(20))

    y = 70
    y = _draw_field(draw, 16, y, "Caller Name", "Jordan Ellis", required=True)
    y = _draw_field(draw, 16, y, "Phone", "(555) 010-4477", required=True)
    y = _draw_field(draw, 16, y, "Call Reason", "Select...", required=True)
    y = _draw_field(draw, 16, y, "Status", "New / Assigned / In Progress / Closed / Escalated", required=True)
    y = _draw_field(draw, 16, y, "Assigned To", "J. Rivera / K. Chen / M. Osei", required=True)

    out = FIXTURES_DIR / "intake-form.png"
    img.save(out)
    print(f"wrote {out}")


def make_caller_detail_sheet():
    img = Image.new("RGB", (520, 230), WHITE)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 520, 50], fill=HEADER_BG)
    draw.text((16, 14), "Caller Detail Sheet", fill=WHITE, font=_font(20))

    y = 70
    y = _draw_field(draw, 16, y, "Caller Name", "Jordan Ellis")
    y = _draw_field(draw, 16, y, "Date of Birth", "03/14/1985")

    out = FIXTURES_DIR / "caller-detail-sheet.png"
    img.save(out)
    print(f"wrote {out}")


if __name__ == "__main__":
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    make_intake_form()
    make_caller_detail_sheet()
