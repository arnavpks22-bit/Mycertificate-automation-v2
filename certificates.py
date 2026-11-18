
from io import BytesIO

from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics

from fonts import register_font


W, H = 841.89, 595.28  # A4 landscape


def create_certificate(
    name,
    background,
    settings,
    custom_font=None
):
    if not name.strip():
        raise ValueError("Participant name is missing")

    if not background:
        raise ValueError("Certificate background is missing")

    font = register_font(
        settings["font"],
        custom_font
    )

    x = W * float(settings["x"]) / 100
    y = H * (1 - float(settings["y"]) / 100)

    max_width = W * float(settings["width"]) / 100
    max_width = min(
        max_width,
        2 * x,
        2 * (W - x)
    )

    if max_width <= 0:
        raise ValueError(
            "Name position is outside certificate"
        )

    size = float(settings["size"])

    while (
        size > 8
        and pdfmetrics.stringWidth(
            name, font, size
        ) > max_width
    ):
        size -= 0.5

    if pdfmetrics.stringWidth(
        name, font, size
    ) > max_width:
        raise ValueError(
            f"Name is too long to fit: {name}"
        )

    output = BytesIO()

    pdf = canvas.Canvas(
        output,
        pagesize=(W, H)
    )

    pdf.drawImage(
        ImageReader(BytesIO(background)),
        0,
        0,
        W,
        H,
        mask="auto"
    )

    pdf.setFillColor(
        HexColor(settings["color"])
    )

    pdf.setFont(font, size)

    pdf.drawCentredString(
        x,
        y - size * 0.33,
        name
    )

    pdf.save()

    return output.getvalue()
