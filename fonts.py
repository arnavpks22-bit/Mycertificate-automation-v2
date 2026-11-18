
"""MiraeTech font catalog and PDF font registration."""

from io import BytesIO
import hashlib

import requests
import streamlit as st

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


FONTS = {
    # Calligraphy
    "Great Vibes": (
        "Calligraphy",
        "greatvibes/GreatVibes-Regular.ttf"
    ),
    "Allura": (
        "Calligraphy",
        "allura/Allura-Regular.ttf"
    ),
    "Alex Brush": (
        "Calligraphy",
        "alexbrush/AlexBrush-Regular.ttf"
    ),
    "Parisienne": (
        "Calligraphy",
        "parisienne/Parisienne-Regular.ttf"
    ),
    "Sacramento": (
        "Calligraphy",
        "sacramento/Sacramento-Regular.ttf"
    ),
    "Tangerine": (
        "Calligraphy",
        "tangerine/Tangerine-Regular.ttf"
    ),

    # Handwriting
    "Pacifico": (
        "Handwriting",
        "pacifico/Pacifico-Regular.ttf"
    ),
    "Lobster": (
        "Handwriting",
        "lobster/Lobster-Regular.ttf"
    ),
    "Satisfy": (
        "Handwriting",
        "satisfy/Satisfy-Regular.ttf"
    ),

    # Elegant
    "Cinzel": (
        "Elegant",
        "cinzel/Cinzel-Regular.ttf"
    ),
    "Cormorant Garamond": (
        "Elegant",
        "cormorantgaramond/CormorantGaramond-Regular.ttf"
    ),
    "Libre Baskerville": (
        "Elegant",
        "librebaskerville/LibreBaskerville-Regular.ttf"
    ),

    # Modern
    "Poppins": (
        "Modern",
        "poppins/Poppins-Regular.ttf"
    ),
    "Poppins SemiBold": (
        "Modern",
        "poppins/Poppins-SemiBold.ttf"
    ),
    "Montserrat": (
        "Modern",
        "montserrat/Montserrat-Regular.ttf"
    ),
    "Roboto": (
        "Modern",
        "roboto/Roboto-Regular.ttf"
    ),
    "Oswald": (
        "Modern",
        "oswald/Oswald-Regular.ttf"
    ),
}


BUILTIN = {
    "Helvetica": "Helvetica",
    "Helvetica Bold": "Helvetica-Bold",
    "Times Roman": "Times-Roman",
}

FONT_NAMES = list(FONTS) + list(BUILTIN)


@st.cache_data(
    show_spinner=False,
    ttl=86400
)
def get_font_bytes(name):
    if name not in FONTS:
        return None

    relative = FONTS[name][1]

    url = (
        "https://raw.githubusercontent.com/"
        "google/fonts/main/ofl/"
        + relative
    )

    response = requests.get(
        url,
        timeout=20
    )

    response.raise_for_status()

    data = response.content

    if data[:4] not in (
        b"\x00\x01\x00\x00",
        b"true",
        b"ttcf"
    ):
        raise ValueError(
            f"{name} did not return a supported "
            "TrueType font. Upload a .ttf file instead."
        )

    return data


def register_font(
    name,
    custom_bytes=None
):
    if custom_bytes:
        data = custom_bytes

    elif name in BUILTIN:
        return BUILTIN[name]

    else:
        data = get_font_bytes(name)

    font_id = (
        "Mirae_"
        + hashlib.sha256(
            data
        ).hexdigest()[:20]
    )

    if font_id not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(
            TTFont(
                font_id,
                BytesIO(data)
            )
        )

    return font_id
