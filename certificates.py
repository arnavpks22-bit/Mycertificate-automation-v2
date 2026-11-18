
from io import BytesIO
from xml.sax.saxutils import escape
import hashlib

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import Paragraph
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


PAGE_WIDTH = 841.89
PAGE_HEIGHT = 595.28

BUILTIN_FONTS = [
    "Helvetica",
    "Helvetica-Bold",
    "Helvetica-Oblique",
    "Times-Roman",
    "Times-Bold",
    "Times-Italic",
    "Courier",
    "Courier-Bold",
    "Courier-Oblique",
]


def register_custom_font(font_bytes):
    """
    Register a TrueType font supplied by the user.
    Returns the registered font name.
    """
    if not font_bytes:
        raise ValueError("Font file is empty.")

    digest = hashlib.sha256(font_bytes).hexdigest()[:16]
    font_name = f"MiraeFont_{digest}"

    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(
            TTFont(font_name, BytesIO(font_bytes))
        )

    return font_name


def create_certificate(
    student,
    background_bytes,
    name_x=50,
    name_y=50,
    name_font_size=30,
    name_color="#073F3B",
    name_width=75,
    name_font="Helvetica-Bold",
    custom_font_bytes=None,
):
    """
    Generate a personalized landscape A4 certificate.

    x and y are percentages measured from top-left.
    Both coordinates represent the name's center.
    """

    name = str(student.get("Name", "")).strip()

    if not name:
        raise ValueError("Participant name is empty.")

    if not background_bytes:
        raise ValueError("Certificate template is required.")

    if not 0 < name_x < 100 or not 0 < name_y < 100:
        raise ValueError("Invalid name coordinates.")

    if not 10 <= name_width <= 100:
        raise ValueError("Invalid name area width.")

    if not 8 <= name_font_size <= 100:
        raise ValueError("Invalid font size.")

    if custom_font_bytes:
        font_name = register_custom_font(custom_font_bytes)
    else:
        if name_font not in BUILTIN_FONTS:
            raise ValueError("Unsupported font.")
        font_name = name_font

    output = BytesIO()

    pdf = canvas.Canvas(
        output,
        pagesize=(PAGE_WIDTH, PAGE_HEIGHT)
    )

    try:
        background = ImageReader(BytesIO(background_bytes))
        pdf.drawImage(
            background,
            0,
            0,
            width=PAGE_WIDTH,
            height=PAGE_HEIGHT,
            preserveAspectRatio=False,
            mask="auto"
        )
    except Exception as error:
        raise ValueError(
            "Could not load certificate background."
        ) from error

    center_x = PAGE_WIDTH * name_x / 100
    center_y = PAGE_HEIGHT * (1 - name_y / 100)

    text_width = PAGE_WIDTH * name_width / 100
    text_width = min(
        text_width,
        2 * min(center_x, PAGE_WIDTH - center_x)
    )

    if text_width <= 0:
        raise ValueError("Name area is outside the page.")

    paragraph = None
    text_height = 0

    for size in range(int(name_font_size), 7, -1):
        style = ParagraphStyle(
            name="ParticipantName",
            fontName=font_name,
            fontSize=size,
            leading=size * 1.15,
            alignment=TA_CENTER,
            textColor=colors.HexColor(name_color),
            spaceBefore=0,
            spaceAfter=0,
            splitLongWords=True,
        )

        paragraph = Paragraph(escape(name), style)

        _, text_height = paragraph.wrap(
            text_width,
            PAGE_HEIGHT
        )

        if text_height <= 48:
            break

    if text_height > 48:
        raise ValueError(
            "Name is too long for the selected area."
        )

    paragraph.drawOn(
        pdf,
        center_x - text_width / 2,
        center_y - text_height / 2
    )

    pdf.showPage()
    pdf.save()

    return output.getvalue()
