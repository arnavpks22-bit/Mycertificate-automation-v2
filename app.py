
import hashlib
import json
import re
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from certificates import BUILTIN_FONTS, create_certificate
from email_service import send_certificate


# ==================================================
# 1. PAGE CONFIGURATION
# ==================================================

st.set_page_config(
    page_title="MiraeTech Certificate Automation",
    page_icon="📜",
    layout="wide",
    initial_sidebar_state="collapsed",
)

STEPS = [
    "Upload",
    "Data",
    "Design",
    "Font",
    "Preview",
    "Email",
]

TEAL = "#137C72"
DARK = "#073F3B"

EMAIL_PATTERN = r"[^@\s]+@[^@\s]+\.[^@\s]+"
TOKEN_PATTERN = r"\{\{\s*([^{}]+?)\s*\}\}"

DEFAULT_FONT_SETTINGS = {
    "name_x": 50,
    "name_y": 50,
    "name_font_size": 30,
    "name_width": 75,
    "name_color": "#073F3B",
    "name_font": "Helvetica-Bold",
}

FONT_PATHS = {
    "Helvetica": [
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ],
    "Helvetica-Bold": [
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ],
    "Helvetica-Oblique": [
        "C:/Windows/Fonts/ariali.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Italic.ttf",
    ],
    "Times-Roman": [
        "C:/Windows/Fonts/times.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf",
    ],
    "Times-Bold": [
        "C:/Windows/Fonts/timesbd.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf",
    ],
    "Times-Italic": [
        "C:/Windows/Fonts/timesi.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSerif-Italic.ttf",
    ],
    "Courier": [
        "C:/Windows/Fonts/cour.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationMono-Regular.ttf",
    ],
    "Courier-Bold": [
        "C:/Windows/Fonts/courbd.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationMono-Bold.ttf",
    ],
    "Courier-Oblique": [
        "C:/Windows/Fonts/couri.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationMono-Italic.ttf",
    ],
}


# ==================================================
# 2. PERSISTENT SESSION STATE
# ==================================================

def initialize_state():
    defaults = {
        "page": 0,
        "spreadsheet_bytes": None,
        "spreadsheet_name": None,
        "raw_data": None,
        "name_column": None,
        "email_column": None,
        "validated": None,
        "validation_report": None,
        "validation_signature": None,
        "certificate_count": 1,
        "templates": {1: None, 2: None},
        "custom_fonts": {1: None, 2: None},
        "font_settings": {
            1: DEFAULT_FONT_SETTINGS.copy(),
            2: DEFAULT_FONT_SETTINGS.copy(),
        },
        "font_confirmed_signature": None,
        "generated_signature": None,
        "records": [],
        "email_subject": "Your Certificate(s)",
        "email_body": (
            "Dear {{Name}},\n\n"
            "Please find your personalized certificate(s) "
            "attached to this email.\n\n"
            "Thank you for participating.\n\n"
            "Best regards,\n"
            "Organizing Team"
        ),
        "send_signature": None,
        "send_results": None,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_state()


# ==================================================
# 3. CUSTOM THEME
# ==================================================

st.markdown(
    """
    <style>
    .stApp {
        background-color: #F2F8F6;
    }

    .block-container {
        max-width: 1250px;
        padding-top: 1rem;
        padding-bottom: 2rem;
    }

    h1, h2, h3 {
        color: #073F3B;
    }

    .mirae-header {
        background: linear-gradient(
            115deg, #073F3B, #137C72
        );
        border-radius: 16px;
        padding: 20px 26px;
        margin-bottom: 16px;
    }

    .mirae-header h2 {
        color: white;
        margin: 0;
        padding: 0;
    }

    .mirae-header p {
        color: #D3ECE6;
        margin: 6px 0 0;
    }

    div.stButton > button[kind="primary"] {
        background-color: #137C72;
        border-color: #137C72;
        color: white;
    }

    div.stButton > button[kind="primary"]:hover {
        background-color: #0B5C55;
        border-color: #0B5C55;
    }

    div[data-testid="stMetric"] {
        background: white;
        border: 1px solid #D8E9E4;
        border-radius: 12px;
        padding: 12px;
    }

    div[data-testid="stFileUploader"] {
        background: white;
        border-radius: 12px;
        padding: 10px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==================================================
# 4. GENERAL HELPERS
# ==================================================

def digest(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def object_hash(value):
    return digest(
        json.dumps(
            value,
            sort_keys=True,
            default=str,
        )
    )


def safe_filename(value):
    return (
        re.sub(
            r"[^A-Za-z0-9_-]+",
            "_",
            str(value)
        ).strip("_")[:60]
        or "Participant"
    )


def render_email(template, student):
    return re.sub(
        TOKEN_PATTERN,
        lambda match: str(
            student.get(match.group(1).strip(), "")
        ),
        template,
    )


def invalidate_email():
    st.session_state.send_signature = None
    st.session_state.send_results = None


def invalidate_generated():
    st.session_state.records = []
    st.session_state.generated_signature = None
    invalidate_email()


def invalidate_fonts():
    st.session_state.font_confirmed_signature = None
    invalidate_generated()


def invalidate_validation():
    st.session_state.validated = None
    st.session_state.validation_report = None
    st.session_state.validation_signature = None
    invalidate_generated()


# ==================================================
# 5. UPLOAD CALLBACKS
# ==================================================

def save_spreadsheet():
    uploaded = st.session_state.get("spreadsheet_widget")

    if uploaded is None:
        return

    raw = uploaded.getvalue()
    new_hash = digest(raw)

    old_bytes = st.session_state.spreadsheet_bytes
    old_hash = digest(old_bytes) if old_bytes else None

    if (
        new_hash == old_hash
        and uploaded.name == st.session_state.spreadsheet_name
    ):
        return

    st.session_state.spreadsheet_bytes = raw
    st.session_state.spreadsheet_name = uploaded.name

    st.session_state.raw_data = None
    st.session_state.name_column = None
    st.session_state.email_column = None

    invalidate_validation()


def save_template(number):
    uploaded = st.session_state.get(
        f"template_widget_{number}"
    )

    if uploaded is None:
        return

    raw = uploaded.getvalue()

    try:
        image = Image.open(BytesIO(raw))
        image.verify()
    except Exception:
        return

    if st.session_state.templates[number] != raw:
        st.session_state.templates[number] = raw
        invalidate_fonts()


def save_custom_font(number):
    uploaded = st.session_state.get(
        f"font_upload_widget_{number}"
    )

    if uploaded is None:
        return

    raw = uploaded.getvalue()

    if st.session_state.custom_fonts[number] != raw:
        st.session_state.custom_fonts[number] = raw
        invalidate_fonts()


def remove_custom_font(number):
    st.session_state.custom_fonts[number] = None
    invalidate_fonts()


def update_font_setting(number, setting):
    widget_key = f"editor_{number}_{setting}"

    new_value = st.session_state[widget_key]

    old_value = st.session_state.font_settings[
        number
    ][setting]

    if old_value != new_value:
        st.session_state.font_settings[
            number
        ][setting] = new_value

        invalidate_fonts()


def update_certificate_count():
    invalidate_fonts()


# ==================================================
# 6. SPREADSHEET PROCESSING
# ==================================================

def load_spreadsheet():
    raw = st.session_state.spreadsheet_bytes
    filename = st.session_state.spreadsheet_name

    if not raw:
        return None

    if filename.lower().endswith(".csv"):
        df = pd.read_csv(
            BytesIO(raw),
            dtype=str,
            keep_default_na=False,
        )
    else:
        df = pd.read_excel(
            BytesIO(raw),
            dtype=str,
            keep_default_na=False,
        )

    return df.fillna("").reset_index(drop=True)


def validate_participants(data):
    df = data.copy().reset_index(drop=True)

    df["Name"] = df["Name"].astype(str).str.strip()
    df["Email"] = df["Email"].astype(str).str.strip()

    duplicate_emails = (
        df["Email"]
        .str.casefold()
        .duplicated(keep=False)
    )

    issues = []

    for index, row in df.iterrows():
        errors = []

        if not row["Name"]:
            errors.append("Missing name")

        if not row["Email"]:
            errors.append("Missing email")

        elif not re.fullmatch(
            EMAIL_PATTERN,
            row["Email"]
        ):
            errors.append("Invalid email")

        if row["Email"] and duplicate_emails.iloc[index]:
            errors.append("Duplicate email")

        issues.append("; ".join(errors))

    report = df.copy()

    report.insert(
        0,
        "Source Row",
        range(2, len(df) + 2),
    )

    report["Issues"] = issues

    report["Status"] = [
        "Ready" if not issue else "Needs correction"
        for issue in issues
    ]

    valid = df.loc[
        report["Status"].eq("Ready")
    ].copy()

    return valid, report


# ==================================================
# 7. FONT PREVIEW
# ==================================================

def load_preview_font(font_name, size, custom_bytes=None):
    size = max(8, int(size))

    if custom_bytes:
        try:
            return ImageFont.truetype(
                BytesIO(custom_bytes),
                size,
            )
        except (OSError, ValueError):
            pass

    for path in FONT_PATHS.get(font_name, []):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue

    return ImageFont.load_default()


def create_image_preview(
    background_bytes,
    name,
    settings,
    custom_font_bytes=None,
):
    image = Image.open(
        BytesIO(background_bytes)
    ).convert("RGB")

    # Keep the preview reasonably fast.
    image.thumbnail((1200, 1200))
    image = image.copy()

    draw = ImageDraw.Draw(image)

    width, height = image.size

    center_x = width * settings["name_x"] / 100
    center_y = height * settings["name_y"] / 100

    text_area_width = (
        width * settings["name_width"] / 100
    )

    text_area_width = min(
        text_area_width,
        2 * min(center_x, width - center_x),
    )

    scale = width / 841.89

    initial_size = max(
        8,
        int(settings["name_font_size"] * scale),
    )

    font = None

    for font_size in range(initial_size, 7, -1):
        font = load_preview_font(
            settings["name_font"],
            font_size,
            custom_font_bytes,
        )

        bbox = draw.textbbox(
            (0, 0),
            name,
            font=font,
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        if (
            text_width <= text_area_width
            and text_height <= 48 * scale
        ):
            break

    draw.text(
        (center_x, center_y),
        name,
        font=font,
        fill=settings["name_color"],
        anchor="mm",
    )

    return image


# ==================================================
# 8. CURRENT CERTIFICATE CONFIGURATION
# ==================================================

def current_templates():
    templates = []

    for number in range(
        1,
        st.session_state.certificate_count + 1,
    ):
        templates.append({
            "number": number,
            "background": (
                st.session_state.templates[number]
            ),
            "settings": (
                st.session_state.font_settings[
                    number
                ].copy()
            ),
            "custom_font_bytes": (
                st.session_state.custom_fonts[
                    number
                ]
            ),
        })

    return templates


def design_signature():
    return object_hash({
        "count": st.session_state.certificate_count,
        "backgrounds": [
            digest(item["background"])
            if item["background"]
            else None
            for item in current_templates()
        ],
    })


def font_signature():
    return object_hash({
        "design": design_signature(),
        "fonts": [
            {
                "number": item["number"],
                "settings": item["settings"],
                "custom_font": (
                    digest(item["custom_font_bytes"])
                    if item["custom_font_bytes"]
                    else None
                ),
            }
            for item in current_templates()
        ],
    })


def data_signature():
    return object_hash({
        "file": (
            digest(st.session_state.spreadsheet_bytes)
            if st.session_state.spreadsheet_bytes
            else None
        ),
        "name": st.session_state.name_column,
        "email": st.session_state.email_column,
    })


def generation_signature():
    return object_hash({
        "data": data_signature(),
        "fonts": font_signature(),
    })


def templates_ready():
    return all(
        item["background"] is not None
        for item in current_templates()
    )


def data_ready():
    return (
        st.session_state.validated is not None
        and not st.session_state.validated.empty
        and st.session_state.validation_signature
        == data_signature()
    )


def fonts_ready():
    return (
        templates_ready()
        and st.session_state.font_confirmed_signature
        == font_signature()
    )


def generation_ready():
    records = st.session_state.records

    return (
        bool(records)
        and st.session_state.generated_signature
        == generation_signature()
        and all(
            len(item["attachments"])
            == st.session_state.certificate_count
            for item in records
        )
    )


def email_ready():
    results = st.session_state.send_results

    return (
        generation_ready()
        and results is not None
        and len(results) == len(st.session_state.records)
        and all(
            item["Status"] != "Not attempted"
            for item in results
        )
    )


# ==================================================
# 9. PROGRESS AND NAVIGATION
# ==================================================

def completion_status():
    return [
        st.session_state.spreadsheet_bytes is not None
        and st.session_state.raw_data is not None,
        data_ready(),
        templates_ready(),
        fonts_ready(),
        generation_ready(),
        email_ready(),
    ]


def navigate(target):
    status = completion_status()

    # Allow users to revisit earlier screens.
    # To move forward, previous steps must be complete.
    if target > 0 and not all(status[:target]):
        st.warning(
            "Complete the earlier steps before continuing."
        )
        return

    st.session_state.page = target
    st.rerun()


def navigation_buttons():
    page = st.session_state.page

    st.divider()

    left, center, right = st.columns([1, 3, 1])

    with left:
        if page > 0:
            if st.button(
                "← Previous",
                use_container_width=True,
            ):
                navigate(page - 1)

    with center:
        st.caption(
            f"Step {page + 1} of {len(STEPS)}"
        )

    with right:
        if page < len(STEPS) - 1:
            if st.button(
                "Next →",
                type="primary",
                use_container_width=True,
            ):
                navigate(page + 1)


# ==================================================
# 10. HEADER AND PROGRESS
# ==================================================

st.markdown(
    """
    <div class="mirae-header">
        <h2>✦ MiraeTech</h2>
        <p>Certificate Automation Workspace</p>
    </div>
    """,
    unsafe_allow_html=True,
)

status = completion_status()
completed = sum(status)

st.progress(
    completed / len(STEPS),
    text=f"{completed} of {len(STEPS)} steps completed",
)

nav_columns = st.columns(6)

for index, column in enumerate(nav_columns):
    with column:
        label = (
            f"✓ {STEPS[index]}"
            if status[index]
            else f"{index + 1}. {STEPS[index]}"
        )

        if st.button(
            label,
            key=f"navigation_{index}",
            type=(
                "primary"
                if st.session_state.page == index
                else "secondary"
            ),
            use_container_width=True,
        ):
            navigate(index)

st.divider()


# ==================================================
# PAGE 1: UPLOAD
# ==================================================

if st.session_state.page == 0:
    st.header("Upload Participant Data")

    st.write(
        "Upload your CSV or Excel file containing "
        "participant names and email addresses."
    )

    st.file_uploader(
        "Choose spreadsheet",
        type=["csv", "xlsx"],
        key="spreadsheet_widget",
        on_change=save_spreadsheet,
    )

    if st.session_state.spreadsheet_bytes:
        try:
            df = load_spreadsheet()

            if df.empty:
                st.error("The spreadsheet is empty.")
                st.session_state.raw_data = None
            else:
                st.session_state.raw_data = df

                st.success(
                    f"{len(df)} participant records loaded."
                )

                st.dataframe(
                    df.head(8),
                    hide_index=True,
                    use_container_width=True,
                )

                st.caption(
                    "Your spreadsheet is saved for "
                    "this browser session."
                )

        except Exception as error:
            st.session_state.raw_data = None
            st.error(f"Unable to read file: {error}")

    navigation_buttons()


# ==================================================
# PAGE 2: DATA
# ==================================================

elif st.session_state.page == 1:
    st.header("Participant Data")

    df = st.session_state.raw_data

    if df is None:
        st.warning("Upload a spreadsheet first.")

    else:
        columns = list(df.columns)

        def suggested_column(names):
            for index, column in enumerate(
                columns, start=1
            ):
                if column.strip().casefold() in names:
                    return index
            return 0

        options = [None] + columns

        left, right = st.columns(2)

        with left:
            name_column = st.selectbox(
                "Name column",
                options,
                index=(
                    options.index(st.session_state.name_column)
                    if st.session_state.name_column in columns
                    else suggested_column([
                        "name",
                        "full name",
                        "student name",
                        "participant name",
                    ])
                ),
                format_func=lambda x: (
                    "Select column" if x is None else x
                ),
            )

        with right:
            email_column = st.selectbox(
                "Email column",
                options,
                index=(
                    options.index(st.session_state.email_column)
                    if st.session_state.email_column in columns
                    else suggested_column([
                        "email",
                        "email address",
                        "student email",
                    ])
                ),
                format_func=lambda x: (
                    "Select column" if x is None else x
                ),
            )

        if (
            name_column != st.session_state.name_column
            or email_column != st.session_state.email_column
        ):
            st.session_state.name_column = name_column
            st.session_state.email_column = email_column
            invalidate_validation()

        if st.button(
            "Validate Participant Data",
            type="primary",
        ):
            if not name_column or not email_column:
                st.error("Select both columns.")

            elif name_column == email_column:
                st.error(
                    "Name and Email must be different columns."
                )

            else:
                mapped = pd.DataFrame({
                    "Name": df[name_column],
                    "Email": df[email_column],
                })

                valid, report = validate_participants(mapped)

                st.session_state.validated = valid
                st.session_state.validation_report = report
                st.session_state.validation_signature = (
                    data_signature()
                )

        report = st.session_state.validation_report

        if report is not None:
            valid = st.session_state.validated

            col1, col2 = st.columns(2)

            col1.metric(
                "Valid Participants",
                len(valid),
            )

            col2.metric(
                "Records With Errors",
                len(report) - len(valid),
            )

            st.dataframe(
                report,
                hide_index=True,
                use_container_width=True,
            )

            invalid = report.loc[
                report["Status"].ne("Ready")
            ]

            if not invalid.empty:
                st.warning(
                    "Correct the invalid records before "
                    "sending the full batch."
                )

                st.download_button(
                    "Download Error Report",
                    invalid.to_csv(
                        index=False
                    ).encode("utf-8-sig"),
                    "validation_errors.csv",
                    "text/csv",
                )

    navigation_buttons()


# ==================================================
# PAGE 3: DESIGN
# ==================================================

elif st.session_state.page == 2:
    st.header("Certificate Design")

    st.write(
        "Choose one or two certificates per participant."
    )

    st.radio(
        "Number of certificates",
        options=[1, 2],
        horizontal=True,
        key="certificate_count",
        on_change=update_certificate_count,
    )

    for number in range(
        1,
        st.session_state.certificate_count + 1
    ):
        st.subheader(f"Certificate {number}")

        st.file_uploader(
            f"Upload Certificate {number} Template",
            type=["png", "jpg", "jpeg"],
            key=f"template_widget_{number}",
            on_change=save_template,
            args=(number,),
        )

        background = st.session_state.templates[number]

        if background:
            try:
                st.image(
                    background,
                    width=520,
                )

                st.success(
                    f"Certificate {number} template saved."
                )

            except Exception as error:
                st.error(
                    f"Invalid template: {error}"
                )

    if templates_ready():
        st.success("All selected templates are ready.")

    navigation_buttons()


# ==================================================
# PAGE 4: LIVE FONT EDITOR
# ==================================================

elif st.session_state.page == 3:
    st.header("Font & Name Placement")

    st.write(
        "Change the font, size, color or position. "
        "The certificate preview updates automatically."
    )

    for number in range(
        1,
        st.session_state.certificate_count + 1
    ):
        st.subheader(f"Certificate {number}")

        background = st.session_state.templates[number]

        if not background:
            st.warning(
                f"Upload Certificate {number} first."
            )
            continue

        settings = st.session_state.font_settings[number]

        # Initialize widget values from persistent settings.
        # These keys may disappear when leaving this page.
        # The persistent dictionary remains available.
        for setting, value in settings.items():
            widget_key = f"editor_{number}_{setting}"

            if widget_key not in st.session_state:
                st.session_state[widget_key] = value

        left, right = st.columns([1.6, 1])

        with right:
            sample_name = st.text_input(
                "Sample participant name",
                value="Sample Participant",
                key=f"sample_name_{number}",
            )

            st.selectbox(
                "Font family",
                BUILTIN_FONTS,
                key=f"editor_{number}_name_font",
                on_change=update_font_setting,
                args=(number, "name_font"),
            )

            st.file_uploader(
                "Optional custom font (.ttf)",
                type=["ttf"],
                key=f"font_upload_widget_{number}",
                on_change=save_custom_font,
                args=(number,),
            )

            if st.session_state.custom_fonts[number]:
                st.caption(
                    "Custom font is active and overrides "
                    "the selected built-in font."
                )

                if st.button(
                    "Remove Custom Font",
                    key=f"remove_font_{number}",
                ):
                    remove_custom_font(number)
                    st.rerun()

            st.slider(
                "Font size",
                min_value=12,
                max_value=72,
                key=f"editor_{number}_name_font_size",
                on_change=update_font_setting,
                args=(number, "name_font_size"),
            )

            st.slider(
                "Horizontal position (%)",
                min_value=5,
                max_value=95,
                key=f"editor_{number}_name_x",
                on_change=update_font_setting,
                args=(number, "name_x"),
            )

            st.slider(
                "Vertical position (%)",
                min_value=5,
                max_value=95,
                key=f"editor_{number}_name_y",
                on_change=update_font_setting,
                args=(number, "name_y"),
            )

            st.slider(
                "Name area width (%)",
                min_value=20,
                max_value=90,
                key=f"editor_{number}_name_width",
                on_change=update_font_setting,
                args=(number, "name_width"),
            )

            st.color_picker(
                "Font color",
                key=f"editor_{number}_name_color",
                on_change=update_font_setting,
                args=(number, "name_color"),
            )

        # Read latest values after controls render.
        settings = st.session_state.font_settings[
            number
        ].copy()

        custom_font_bytes = (
            st.session_state.custom_fonts[number]
        )

        with left:
            try:
                preview = create_image_preview(
                    background,
                    sample_name or "Sample Participant",
                    settings,
                    custom_font_bytes,
                )

                st.image(
                    preview,
                    use_container_width=True,
                )

                st.caption(
                    "Live image preview. Download the "
                    "sample PDF for exact rendering."
                )

                sample_pdf = create_certificate(
                    {
                        "Name": (
                            sample_name
                            or "Sample Participant"
                        )
                    },
                    background_bytes=background,
                    custom_font_bytes=custom_font_bytes,
                    **settings,
                )

                st.download_button(
                    f"Download Certificate {number} Sample PDF",
                    data=sample_pdf,
                    file_name=(
                        f"certificate_{number}_sample.pdf"
                    ),
                    mime="application/pdf",
                    key=f"sample_pdf_{number}",
                )

            except Exception as error:
                st.error(
                    f"Preview error: {error}"
                )

        st.divider()

    if st.button(
        "Confirm Font & Position Settings",
        type="primary",
    ):
        try:
            for item in current_templates():
                create_certificate(
                    {"Name": "Sample Participant"},
                    background_bytes=item["background"],
                    custom_font_bytes=item["custom_font_bytes"],
                    **item["settings"],
                )

            st.session_state.font_confirmed_signature = (
                font_signature()
            )

            st.success(
                "Font and position settings confirmed."
            )

        except Exception as error:
            st.error(
                f"Cannot confirm settings: {error}"
            )

    if fonts_ready():
        st.success(
            "Font customization is complete."
        )

    navigation_buttons()


# ==================================================
# PAGE 5: GENERATE AND PREVIEW
# ==================================================

elif st.session_state.page == 4:
    st.header("Generate & Preview Certificates")

    valid = st.session_state.validated
    templates = current_templates()

    if not data_ready() or not fonts_ready():
        st.warning(
            "Complete Data, Design and Font steps first."
        )

    else:
        expected = (
            len(valid)
            * st.session_state.certificate_count
        )

        st.info(
            f"{len(valid)} participants · "
            f"{expected} certificate PDFs"
        )

        if st.button(
            "Generate All Certificates",
            type="primary",
        ):
            records = []
            progress = st.progress(0)

            for index, (source_index, row) in enumerate(
                valid.iterrows(),
                start=1,
            ):
                student = row.to_dict()
                attachments = []
                error = ""

                try:
                    for item in templates:
                        pdf = create_certificate(
                            student,
                            background_bytes=item["background"],
                            custom_font_bytes=(
                                item["custom_font_bytes"]
                            ),
                            **item["settings"],
                        )

                        filename = (
                            f"{index:04d}_"
                            f"{safe_filename(student['Name'])}_"
                            f"Certificate_{item['number']}.pdf"
                        )

                        attachments.append(
                            (filename, pdf)
                        )

                except Exception as exc:
                    error = str(exc)
                    attachments = []

                records.append({
                    "student": student,
                    "attachments": attachments,
                    "source_row": int(source_index) + 2,
                    "error": error,
                })

                progress.progress(index / len(valid))

            st.session_state.records = records
            st.session_state.generated_signature = (
                generation_signature()
            )

            invalidate_email()

        records = st.session_state.records

        successful = [
            item for item in records
            if len(item["attachments"])
            == st.session_state.certificate_count
        ]

        failed = [
            item for item in records
            if len(item["attachments"])
            != st.session_state.certificate_count
        ]

        if failed:
            st.error(
                f"{len(failed)} participant(s) failed."
            )

            st.dataframe(
                pd.DataFrame([
                    {
                        "Row": item["source_row"],
                        "Name": item["student"]["Name"],
                        "Error": item["error"],
                    }
                    for item in failed
                ]),
                hide_index=True,
                use_container_width=True,
            )

        if successful:
            st.success(
                f"Generated {sum(len(x['attachments']) for x in successful)} "
                "certificates successfully."
            )

            zip_buffer = BytesIO()

            with ZipFile(
                zip_buffer,
                "w",
                ZIP_DEFLATED,
            ) as archive:
                for item in successful:
                    for filename, pdf in item["attachments"]:
                        archive.writestr(
                            filename,
                            pdf,
                        )

            st.download_button(
                "Download All Certificates (ZIP)",
                data=zip_buffer.getvalue(),
                file_name="miraetech_certificates.zip",
                mime="application/zip",
                type="primary",
            )

            selected = st.selectbox(
                "Choose participant to preview",
                range(len(successful)),
                format_func=lambda i: (
                    successful[i]["student"]["Name"]
                ),
            )

            chosen = successful[selected]

            for index, (filename, pdf) in enumerate(
                chosen["attachments"],
                start=1,
            ):
                st.download_button(
                    f"Download Certificate {index}",
                    data=pdf,
                    file_name=filename,
                    mime="application/pdf",
                    key=f"preview_pdf_{index}",
                )

    navigation_buttons()


# ==================================================
# PAGE 6: EMAIL
# ==================================================

elif st.session_state.page == 5:
    st.header("Email Delivery")

    records = [
        item
        for item in st.session_state.records
        if len(item["attachments"])
        == st.session_state.certificate_count
    ]

    if not generation_ready():
        st.warning(
            "Generate all certificates successfully first."
        )

    else:
        st.metric(
            "Participants",
            len(records),
        )

        subject = st.text_input(
            "Email subject",
            key="email_subject",
        )

        body = st.text_area(
            "Email message",
            height=160,
            key="email_body",
        )

        st.caption(
            "Available placeholders: {{Name}}, {{Email}}"
        )

        selected = st.selectbox(
            "Preview recipient",
            range(len(records)),
            format_func=lambda i: (
                records[i]["student"]["Name"]
            ),
        )

        sample = records[selected]

        st.write(
            "**To:**",
            sample["student"]["Email"],
        )

        st.write(
            "**Subject:**",
            render_email(
                subject,
                sample["student"],
            ),
        )

        st.text(
            render_email(
                body,
                sample["student"],
            )
        )

        st.write(
            "**PDF attachments:**",
            len(sample["attachments"]),
        )

        for filename, _ in sample["attachments"]:
            st.caption(filename)

        st.divider()

        sender = st.text_input(
            "Sender Gmail address",
            key="sender_email",
        ).strip()

        password = st.text_input(
            "Gmail App Password",
            type="password",
            key="gmail_password",
        ).replace(" ", "")

        st.caption(
            "Use a Google App Password, not your "
            "normal Gmail password."
        )

        unknown_tokens = {
            token.strip()
            for token in re.findall(
                TOKEN_PATTERN,
                subject + "\n" + body,
            )
            if token.strip() not in ("Name", "Email")
        }

        if unknown_tokens:
            st.error(
                "Unknown placeholders: "
                + ", ".join(sorted(unknown_tokens))
            )

        valid_sender = bool(
            re.fullmatch(EMAIL_PATTERN, sender)
        )

        valid_message = bool(
            subject.strip()
            and body.strip()
            and "\n" not in subject
            and "\r" not in subject
            and not unknown_tokens
        )

        batch_signature = object_hash({
            "generation": generation_signature(),
            "subject": subject,
            "body": body,
            "sender": sender,
        })

        if (
            st.session_state.send_signature
            != batch_signature
        ):
            st.session_state.send_signature = (
                batch_signature
            )
            st.session_state.send_results = None

        if st.session_state.send_results is not None:
            st.warning(
                "This email batch was already attempted "
                "during this session. Check Gmail Sent "
                "before attempting it again."
            )

        confirmed = st.checkbox(
            "I have checked the recipients and "
            "authorize sending these certificates."
        )

        can_send = (
            valid_sender
            and len(password) == 16
            and valid_message
            and confirmed
            and st.session_state.send_results is None
        )

        if st.button(
            "Send Certificates",
            type="primary",
            disabled=not can_send,
        ):
            results = [
                {
                    "Name": item["student"]["Name"],
                    "Email": item["student"]["Email"],
                    "Attachments": len(item["attachments"]),
                    "Status": "Not attempted",
                }
                for item in records
            ]

            st.session_state.send_results = results

            progress = st.progress(0)

            for index, record in enumerate(records):
                student = record["student"]

                results[index]["Status"] = (
                    "Attempted - awaiting result"
                )

                try:
                    send_certificate(
                        sender=sender,
                        app_password=password,
                        recipient=student["Email"],
                        subject=render_email(
                            subject,
                            student,
                        ),
                        body=render_email(
                            body,
                            student,
                        ),
                        attachments=record["attachments"],
                    )

                    results[index]["Status"] = (
                        "Accepted by Gmail"
                    )

                except Exception as error:
                    results[index]["Status"] = (
                        "Not confirmed - check Gmail Sent"
                    )

                    st.warning(
                        f"{student['Email']}: {error}"
                    )

                progress.progress(
                    (index + 1) / len(records)
                )

            st.session_state.send_results = results

        if st.session_state.send_results is not None:
            report = pd.DataFrame(
                st.session_state.send_results
            )

            st.subheader("Sending Report")

            st.dataframe(
                report,
                hide_index=True,
                use_container_width=True,
            )

            st.download_button(
                "Download Sending Report",
                data=report.to_csv(
                    index=False
                ).encode("utf-8-sig"),
                file_name="sending_report.csv",
                mime="text/csv",
            )

            st.caption(
                "Gmail accepting an email does not "
                "guarantee inbox delivery."
            )

    navigation_buttons()
