
import hashlib
import json
import re
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from certificates import (
    BUILTIN_FONTS,
    create_certificate,
)
from email_service import send_certificate


# ==========================================
# PAGE CONFIGURATION
# ==========================================

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

FONT_FILES = {
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


# ==========================================
# SESSION STATE
# ==========================================

DEFAULTS = {
    "page": 0,
    "upload_hash": None,
    "data_hash": None,
    "design_hash": None,
    "font_hash": None,
    "generated_hash": None,
    "records": [],
    "validated": None,
    "validation_report": None,
    "send_hash": None,
    "send_results": None,
    "font_confirmed": False,
    "certificate_count": 1,
    "email_subject": "Your Certificates",
    "email_body": (
        "Dear {{Name}},\n\n"
        "Please find your personalized certificate(s) "
        "attached.\n\n"
        "Thank you for participating.\n\n"
        "Best regards,\n"
        "Organizing Team"
    ),
}

for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ==========================================
# STYLING
# ==========================================

st.markdown(
    """
    <style>
    .stApp {
        background: #F2F8F6;
        color: #073F3B;
    }

    .block-container {
        max-width: 1200px;
        padding-top: 1rem;
        padding-bottom: 1.5rem;
    }

    h1, h2, h3 {
        color: #073F3B;
    }

    div.stButton > button[kind="primary"] {
        background: #137C72;
        border-color: #137C72;
        color: white;
    }

    div.stButton > button[kind="primary"]:hover {
        background: #0B5C55;
        border-color: #0B5C55;
    }

    div[data-testid="stMetric"] {
        background: white;
        border: 1px solid #D9EAE5;
        border-radius: 12px;
        padding: 14px;
    }

    div[data-testid="stFileUploader"] {
        background: white;
        border-radius: 12px;
        padding: 10px;
    }

    .mirae-header {
        background: linear-gradient(
            110deg, #073F3B, #137C72
        );
        border-radius: 16px;
        padding: 18px 24px;
        color: white;
        margin-bottom: 14px;
    }

    .mirae-header h2 {
        color: white;
        margin: 0;
    }

    .mirae-header p {
        color: #CDE7E2;
        margin: 4px 0 0;
    }

    .step-label {
        color: #073F3B;
        font-weight: 600;
        font-size: 13px;
        text-align: center;
        padding: 7px 2px;
        border-radius: 7px;
        background: #E2EEEB;
    }

    .step-active {
        color: white;
        background: #137C72;
    }

    .step-done {
        background: #CDEFE5;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==========================================
# GENERAL HELPERS
# ==========================================

def digest(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hash_object(value):
    return digest(
        json.dumps(
            value,
            sort_keys=True,
            default=str
        )
    )


def clear_generated():
    st.session_state.records = []
    st.session_state.generated_hash = None
    st.session_state.send_results = None
    st.session_state.send_hash = None


def clear_validation():
    st.session_state.validated = None
    st.session_state.validation_report = None
    clear_generated()


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
        template
    )


def load_spreadsheet(uploaded):
    raw = uploaded.getvalue()

    if uploaded.name.lower().endswith(".csv"):
        df = pd.read_csv(
            BytesIO(raw),
            dtype=str,
            keep_default_na=False
        )
    else:
        df = pd.read_excel(
            BytesIO(raw),
            dtype=str,
            keep_default_na=False
        )

    return df.fillna("").reset_index(drop=True)


def validate_data(df):
    result = df.copy().reset_index(drop=True)

    result["Name"] = (
        result["Name"].astype(str).str.strip()
    )
    result["Email"] = (
        result["Email"].astype(str).str.strip()
    )

    issues = []

    duplicate_emails = (
        result["Email"]
        .str.casefold()
        .duplicated(keep=False)
    )

    for index, row in result.iterrows():
        problems = []

        if not row["Name"]:
            problems.append("Missing name")

        if not row["Email"]:
            problems.append("Missing email")
        elif not re.fullmatch(
            EMAIL_PATTERN,
            row["Email"]
        ):
            problems.append("Invalid email")

        if row["Email"] and duplicate_emails.iloc[index]:
            problems.append("Duplicate email")

        issues.append("; ".join(problems))

    report = result.copy()
    report.insert(
        0, "Source Row",
        range(2, len(result) + 2)
    )
    report["Issues"] = issues
    report["Status"] = [
        "Ready" if not x else "Needs correction"
        for x in issues
    ]

    valid = result.loc[
        report["Status"].eq("Ready")
    ].copy()

    return valid, report


def load_font(font_name, size, custom_bytes=None):
    size = max(8, int(size))

    if custom_bytes:
        try:
            return ImageFont.truetype(
                BytesIO(custom_bytes),
                size
            )
        except (OSError, ValueError):
            pass

    for path in FONT_FILES.get(font_name, []):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue

    return ImageFont.load_default()


def image_preview(background, name, settings):
    image = Image.open(
        BytesIO(background)
    ).convert("RGB")

    image.thumbnail((1200, 1200))
    image = image.copy()

    draw = ImageDraw.Draw(image)
    width, height = image.size

    x = width * settings["name_x"] / 100
    y = height * settings["name_y"] / 100

    available = width * settings["name_width"] / 100
    available = min(
        available,
        2 * min(x, width - x)
    )

    scale = width / 841.89
    custom = settings.get("custom_font_bytes")

    font = load_font(
        settings["name_font"],
        settings["name_font_size"] * scale,
        custom
    )

    for size in range(
        max(8, int(settings["name_font_size"] * scale)),
        7,
        -1
    ):
        font = load_font(
            settings["name_font"],
            size,
            custom
        )

        bbox = draw.textbbox(
            (0, 0), name, font=font
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        if (
            text_width <= available
            and text_height <= 48 * scale
        ):
            break

    draw.text(
        (x, y),
        name,
        font=font,
        fill=settings["name_color"],
        anchor="mm"
    )

    return image


def certificate_settings(number):
    return {
        "name_x": st.session_state.get(
            f"x_{number}", 50
        ),
        "name_y": st.session_state.get(
            f"y_{number}", 50
        ),
        "name_font_size": st.session_state.get(
            f"size_{number}", 30
        ),
        "name_width": st.session_state.get(
            f"width_{number}", 75
        ),
        "name_color": st.session_state.get(
            f"color_{number}", "#073F3B"
        ),
        "name_font": st.session_state.get(
            f"font_{number}", "Helvetica-Bold"
        ),
    }


def current_templates():
    result = []

    for number in range(
        1,
        st.session_state.certificate_count + 1
    ):
        background = st.session_state.get(
            f"template_{number}"
        )

        font_file = st.session_state.get(
            f"custom_font_{number}"
        )

        settings = certificate_settings(number)

        settings["custom_font_bytes"] = (
            font_file.getvalue()
            if font_file is not None
            else None
        )

        result.append({
            "number": number,
            "background": (
                background.getvalue()
                if background is not None
                else None
            ),
            "settings": settings,
        })

    return result


def template_signature(templates, include_fonts=False):
    items = []

    for item in templates:
        settings = item["settings"].copy()
        custom_bytes = settings.pop(
            "custom_font_bytes", None
        )

        entry = {
            "number": item["number"],
            "background": (
                digest(item["background"])
                if item["background"]
                else None
            ),
        }

        if include_fonts:
            entry["settings"] = settings
            entry["custom_font"] = (
                digest(custom_bytes)
                if custom_bytes
                else None
            )

        items.append(entry)

    return hash_object(items)


def all_templates_ready(templates):
    return bool(templates) and all(
        item["background"]
        for item in templates
    )


# ==========================================
# COMPLETION AND NAVIGATION
# ==========================================

def completion_status():
    upload_done = (
        st.session_state.upload_hash is not None
    )

    data_done = (
        st.session_state.validated is not None
        and not st.session_state.validated.empty
    )

    templates = current_templates()

    design_done = all_templates_ready(templates)

    font_done = (
        design_done
        and st.session_state.font_confirmed
    )

    preview_done = (
        font_done
        and bool(st.session_state.records)
        and all(
            len(record["attachments"])
            == st.session_state.certificate_count
            for record in st.session_state.records
        )
    )

    email_done = (
        preview_done
        and st.session_state.send_results is not None
        and all(
            item["Status"] != "Not attempted"
            for item in st.session_state.send_results
        )
    )

    return [
        upload_done,
        data_done,
        design_done,
        font_done,
        preview_done,
        email_done,
    ]


def navigate(target):
    status = completion_status()

    # A user can revisit completed screens.
    # Moving forward requires earlier steps.
    if target > st.session_state.page:
        if not all(status[:target]):
            st.warning(
                "Complete the previous steps first."
            )
            return

    st.session_state.page = target
    st.rerun()


def show_navigation():
    page = st.session_state.page

    st.divider()

    left, middle, right = st.columns(
        [1, 3, 1]
    )

    with left:
        if page > 0:
            if st.button(
                "← Previous",
                use_container_width=True
            ):
                navigate(page - 1)

    with middle:
        st.caption(
            f"Step {page + 1} of {len(STEPS)}"
        )

    with right:
        if page < len(STEPS) - 1:
            if st.button(
                "Next →",
                type="primary",
                use_container_width=True
            ):
                navigate(page + 1)


# ==========================================
# HEADER AND PROGRESS BAR
# ==========================================

st.markdown(
    """
    <div class="mirae-header">
        <h2>✦ MiraeTech</h2>
        <p>Certificate Automation Workspace</p>
    </div>
    """,
    unsafe_allow_html=True
)

status = completion_status()
completed_count = sum(status)

st.progress(
    completed_count / len(STEPS),
    text=(
        f"{completed_count} of {len(STEPS)} "
        "steps completed"
    )
)

step_columns = st.columns(6)

for index, column in enumerate(step_columns):
    with column:
        active = index == st.session_state.page

        label = (
            f"✓ {STEPS[index]}"
            if status[index]
            else f"{index + 1}. {STEPS[index]}"
        )

        if st.button(
            label,
            key=f"nav_{index}",
            type="primary" if active else "secondary",
            use_container_width=True
        ):
            navigate(index)

st.divider()


# ==========================================
# PAGE 1: UPLOAD
# ==========================================

if st.session_state.page == 0:
    st.header("Upload Participant Data")

    st.write(
        "Upload a CSV or Excel file containing "
        "participant names and email addresses."
    )

    uploaded = st.file_uploader(
        "Choose CSV or Excel file",
        type=["csv", "xlsx"],
        key="spreadsheet"
    )

    if uploaded is not None:
        try:
            df = load_spreadsheet(uploaded)

            if df.empty:
                st.error("The spreadsheet is empty.")
            else:
                new_hash = digest(uploaded.getvalue())

                if new_hash != st.session_state.upload_hash:
                    st.session_state.upload_hash = new_hash
                    clear_validation()

                st.session_state["raw_data"] = df

                st.success(
                    f"{len(df)} participant records loaded."
                )

                st.dataframe(
                    df.head(8),
                    hide_index=True,
                    use_container_width=True
                )

        except Exception as error:
            st.session_state.upload_hash = None
            clear_validation()
            st.error(f"Upload error: {error}")

    else:
        if st.session_state.upload_hash is not None:
            st.session_state.upload_hash = None
            st.session_state.pop("raw_data", None)
            clear_validation()

    show_navigation()


# ==========================================
# PAGE 2: DATA VALIDATION
# ==========================================

elif st.session_state.page == 1:
    st.header("Participant Data")

    df = st.session_state.get("raw_data")

    if df is None:
        st.warning("Upload a spreadsheet first.")

    else:
        columns = list(df.columns)

        def suggested(aliases):
            for index, column in enumerate(
                columns, start=1
            ):
                if column.strip().casefold() in aliases:
                    return index
            return 0

        options = [None] + columns

        left, right = st.columns(2)

        with left:
            name_column = st.selectbox(
                "Name column",
                options,
                index=suggested([
                    "name", "full name",
                    "participant name", "student name"
                ]),
                format_func=lambda x: (
                    "Select column" if x is None else x
                ),
                key="name_mapping"
            )

        with right:
            email_column = st.selectbox(
                "Email column",
                options,
                index=suggested([
                    "email", "email address",
                    "student email"
                ]),
                format_func=lambda x: (
                    "Select column" if x is None else x
                ),
                key="email_mapping"
            )

        mapping_hash = hash_object({
            "upload": st.session_state.upload_hash,
            "name": name_column,
            "email": email_column,
        })

        if mapping_hash != st.session_state.data_hash:
            st.session_state.data_hash = mapping_hash
            clear_validation()

        if st.button(
            "Validate Data",
            type="primary"
        ):
            if not name_column or not email_column:
                st.error("Select both columns.")

            elif name_column == email_column:
                st.error(
                    "Name and Email must use different columns."
                )

            else:
                mapped = pd.DataFrame({
                    "Name": df[name_column],
                    "Email": df[email_column],
                })

                valid, report = validate_data(mapped)

                st.session_state.validated = valid
                st.session_state.validation_report = report

        report = st.session_state.validation_report

        if report is not None:
            valid = st.session_state.validated

            c1, c2 = st.columns(2)

            c1.metric("Valid", len(valid))
            c2.metric(
                "Needs Correction",
                len(report) - len(valid)
            )

            st.dataframe(
                report,
                hide_index=True,
                use_container_width=True
            )

            invalid = report.loc[
                report["Status"].ne("Ready")
            ]

            if not invalid.empty:
                st.download_button(
                    "Download Error Report",
                    invalid.to_csv(
                        index=False
                    ).encode("utf-8-sig"),
                    "validation_errors.csv",
                    "text/csv"
                )

    show_navigation()


# ==========================================
# PAGE 3: CERTIFICATE DESIGN
# ==========================================

elif st.session_state.page == 2:
    st.header("Certificate Design")

    st.write(
        "Choose how many certificates each "
        "participant should receive."
    )

    certificate_count = st.radio(
        "Certificates per participant",
        [1, 2],
        horizontal=True,
        key="certificate_count"
    )

    st.caption(
        "Each participant receives one email "
        "with the selected number of PDFs."
    )

    for number in range(1, certificate_count + 1):
        st.subheader(f"Certificate {number}")

        template = st.file_uploader(
            f"Upload Template {number}",
            type=["png", "jpg", "jpeg"],
            key=f"template_{number}"
        )

        if template:
            try:
                image = Image.open(
                    BytesIO(template.getvalue())
                )
                image.verify()

                st.image(
                    template.getvalue(),
                    width=500
                )

            except Exception:
                st.error(
                    f"Certificate {number} is not a valid image."
                )

    templates = current_templates()
    new_design_hash = template_signature(templates)

    if new_design_hash != st.session_state.design_hash:
        st.session_state.design_hash = new_design_hash
        st.session_state.font_confirmed = False
        clear_generated()

    if all_templates_ready(templates):
        st.success(
            "All selected certificate templates uploaded."
        )

    show_navigation()


# ==========================================
# PAGE 4: FONT AND POSITION EDITOR
# ==========================================

elif st.session_state.page == 3:
    st.header("Font & Name Placement")

    st.write(
        "Customize each certificate independently. "
        "The preview updates when you change settings."
    )

    templates = current_templates()

    for item in templates:
        number = item["number"]
        background = item["background"]

        st.subheader(f"Certificate {number}")

        left, right = st.columns([1.6, 1])

        with right:
            sample_name = st.text_input(
                "Sample participant name",
                value="Sample Participant",
                key=f"sample_{number}"
            )

            font_choice = st.selectbox(
                "Font family",
                BUILTIN_FONTS,
                index=1,
                key=f"font_{number}"
            )

            custom_font = st.file_uploader(
                "Optional custom TrueType font (.ttf)",
                type=["ttf"],
                key=f"custom_font_{number}"
            )

            font_size = st.slider(
                "Font size",
                12, 72, 30,
                key=f"size_{number}"
            )

            x = st.slider(
                "Horizontal position (%)",
                5, 95, 50,
                key=f"x_{number}"
            )

            y = st.slider(
                "Vertical position (%)",
                5, 95, 50,
                key=f"y_{number}"
            )

            width = st.slider(
                "Name area width (%)",
                20, 90, 75,
                key=f"width_{number}"
            )

            color = st.color_picker(
                "Font color",
                "#073F3B",
                key=f"color_{number}"
            )

        settings = certificate_settings(number)

        settings["custom_font_bytes"] = (
            custom_font.getvalue()
            if custom_font
            else None
        )

        with left:
            if background:
                try:
                    preview = image_preview(
                        background,
                        sample_name or "Sample Participant",
                        settings
                    )

                    st.image(
                        preview,
                        use_container_width=True
                    )

                    sample_pdf = create_certificate(
                        {
                            "Name": (
                                sample_name
                                or "Sample Participant"
                            )
                        },
                        background_bytes=background,
                        **settings
                    )

                    st.download_button(
                        f"Download Certificate {number} Sample PDF",
                        sample_pdf,
                        f"sample_certificate_{number}.pdf",
                        "application/pdf",
                        key=f"pdf_sample_{number}"
                    )

                except Exception as error:
                    st.error(
                        f"Preview error: {error}"
                    )

        st.divider()

    templates = current_templates()

    new_font_hash = template_signature(
        templates,
        include_fonts=True
    )

    if new_font_hash != st.session_state.font_hash:
        st.session_state.font_hash = new_font_hash
        st.session_state.font_confirmed = False
        clear_generated()

    if st.button(
        "Confirm Font & Position Settings",
        type="primary"
    ):
        st.session_state.font_confirmed = True
        st.success("Font settings confirmed.")

    if st.session_state.font_confirmed:
        st.success(
            "Certificate customization is complete."
        )

    show_navigation()


# ==========================================
# PAGE 5: GENERATE AND PREVIEW
# ==========================================

elif st.session_state.page == 4:
    st.header("Generate & Preview")

    valid = st.session_state.validated
    templates = current_templates()

    if valid is None or valid.empty:
        st.warning("Validate participant data first.")

    else:
        expected = (
            len(valid)
            * st.session_state.certificate_count
        )

        st.info(
            f"{len(valid)} participants · "
            f"{expected} PDF certificates"
        )

        if st.button(
            "Generate Certificates",
            type="primary"
        ):
            records = []
            progress = st.progress(0)

            for index, (_, row) in enumerate(
                valid.iterrows(),
                start=1
            ):
                student = row.to_dict()
                attachments = []
                error = ""

                try:
                    for item in templates:
                        pdf = create_certificate(
                            student,
                            background_bytes=item["background"],
                            **item["settings"]
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
                    "error": error,
                })

                progress.progress(index / len(valid))

            st.session_state.records = records
            st.session_state.generated_hash = (
                st.session_state.font_hash
            )
            st.session_state.send_results = None
            st.session_state.send_hash = None

        records = st.session_state.records

        successful = [
            record for record in records
            if len(record["attachments"])
            == st.session_state.certificate_count
        ]

        failed = [
            record for record in records
            if record not in successful
        ]

        if failed:
            st.error(
                f"{len(failed)} participants failed."
            )

            st.dataframe(
                pd.DataFrame([
                    {
                        "Name": item["student"]["Name"],
                        "Error": item["error"]
                    }
                    for item in failed
                ]),
                hide_index=True
            )

        if successful:
            st.success(
                f"{len(successful)} participants processed."
            )

            archive_bytes = BytesIO()

            with ZipFile(
                archive_bytes,
                "w",
                ZIP_DEFLATED
            ) as archive:
                for record in successful:
                    for filename, pdf in record["attachments"]:
                        archive.writestr(filename, pdf)

            st.download_button(
                "Download All Certificates (ZIP)",
                archive_bytes.getvalue(),
                "miraetech_certificates.zip",
                "application/zip",
                type="primary"
            )

            selected = st.selectbox(
                "Preview participant",
                range(len(successful)),
                format_func=lambda i: (
                    successful[i]["student"]["Name"]
                )
            )

            chosen = successful[selected]

            for filename, pdf in chosen["attachments"]:
                st.download_button(
                    f"Download {filename}",
                    pdf,
                    filename,
                    "application/pdf",
                    key=f"preview_{filename}"
                )

    show_navigation()


# ==========================================
# PAGE 6: EMAIL
# ==========================================

elif st.session_state.page == 5:
    st.header("Email Delivery")

    records = [
        record
        for record in st.session_state.records
        if len(record["attachments"])
        == st.session_state.certificate_count
    ]

    if not records:
        st.warning("Generate certificates first.")

    else:
        st.metric(
            "Emails to send",
            len(records)
        )

        subject = st.text_input(
            "Email subject",
            key="email_subject"
        )

        body = st.text_area(
            "Email message",
            height=160,
            key="email_body"
        )

        st.caption(
            "Placeholders: {{Name}} and {{Email}}"
        )

        selected = st.selectbox(
            "Preview recipient",
            range(len(records)),
            format_func=lambda i: (
                records[i]["student"]["Name"]
            )
        )

        sample = records[selected]

        st.write(
            "**To:**",
            sample["student"]["Email"]
        )

        st.write(
            "**Subject:**",
            render_email(
                subject,
                sample["student"]
            )
        )

        st.text(
            render_email(
                body,
                sample["student"]
            )
        )

        st.write(
            "**Attachments:**",
            len(sample["attachments"])
        )

        for filename, _ in sample["attachments"]:
            st.caption(filename)

        st.divider()

        sender = st.text_input(
            "Sender Gmail address",
            key="sender_email"
        ).strip()

        password = st.text_input(
            "Gmail App Password",
            type="password",
            key="gmail_password"
        ).replace(" ", "")

        st.caption(
            "Use a Gmail App Password, "
            "not your regular Google password."
        )

        unknown_tokens = {
            token.strip()
            for token in re.findall(
                TOKEN_PATTERN,
                subject + "\n" + body
            )
            if token.strip() not in ("Name", "Email")
        }

        valid_email = bool(
            re.fullmatch(EMAIL_PATTERN, sender)
        )

        valid_message = bool(
            subject.strip()
            and body.strip()
            and "\n" not in subject
            and "\r" not in subject
            and not unknown_tokens
        )

        if unknown_tokens:
            st.error(
                "Unknown placeholders: "
                + ", ".join(sorted(unknown_tokens))
            )

        batch_hash = hash_object({
            "generated": st.session_state.generated_hash,
            "subject": subject,
            "body": body,
            "sender": sender,
        })

        if batch_hash != st.session_state.send_hash:
            st.session_state.send_hash = batch_hash
            st.session_state.send_results = None

        if st.session_state.send_results is not None:
            st.warning(
                "This batch was already attempted "
                "during this session. Check Gmail Sent "
                "before attempting it again."
            )

        confirmed = st.checkbox(
            "I verified the recipients and "
            "authorize sending these certificates."
        )

        can_send = (
            valid_email
            and len(password) == 16
            and valid_message
            and confirmed
            and st.session_state.send_results is None
        )

        if st.button(
            "Send Certificates",
            type="primary",
            disabled=not can_send
        ):
            results = [
                {
                    "Name": item["student"]["Name"],
                    "Email": item["student"]["Email"],
                    "Status": "Not attempted"
                }
                for item in records
            ]

            # Save before sending to help avoid
            # accidental repeated submissions.
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
                            student
                        ),
                        body=render_email(
                            body,
                            student
                        ),
                        attachments=record["attachments"]
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
                use_container_width=True
            )

            st.download_button(
                "Download Sending Report",
                report.to_csv(
                    index=False
                ).encode("utf-8-sig"),
                "sending_report.csv",
                "text/csv"
            )

            st.caption(
                "Gmail acceptance does not guarantee "
                "delivery to the recipient's inbox."
            )

    show_navigation()
