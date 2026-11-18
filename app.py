
import base64
import hashlib
import json
import re
import time

from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from PIL import Image

from certificates import create_certificate
from email_service import send_certificate


# ==================================================
# APPLICATION CONFIGURATION
# ==================================================

st.set_page_config(
    page_title="MiraeTech Certificates",
    page_icon="🏅",
    layout="wide"
)

EDITOR = components.declare_component(
    "mirae_live_editor",
    path=str(
        Path(__file__).parent / "certificate_editor"
    )
)

STEPS = [
    "Upload",
    "Data",
    "Design",
    "Font",
    "Preview",
    "Email"
]

DEFAULT_STYLE = {
    "font": "Great Vibes",
    "size": 42,
    "x": 50,
    "y": 50,
    "width": 75,
    "color": "#073f3b"
}


# ==================================================
# CUSTOM STYLING
# ==================================================

st.markdown(
    """
    <style>
    .block-container {
        max-width: 1260px;
        padding-top: 1.1rem;
    }

    .mirae {
        background: linear-gradient(
            110deg, #073f3b, #137c72
        );
        border-radius: 16px;
        padding: 18px 24px;
        color: white;
        margin-bottom: 15px;
    }

    .mirae h2 {
        color: white;
        margin: 0;
    }

    .mirae p {
        margin: 4px 0;
        color: #d5f1e9;
    }

    div.stButton > button[kind="primary"] {
        background: #137c72;
        border-color: #137c72;
    }

    div[data-testid="stProgress"] > div > div {
        background-color: #137c72;
    }

    div[data-testid="stStatusWidget"] {
        border-radius: 12px;
    }

    div[data-testid="stSpinner"] {
        color: #137c72;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# ==================================================
# SESSION STATE
# ==================================================

def initialize():
    defaults = {
        "page": 0,
        "source_bytes": None,
        "source_name": None,
        "df": None,
        "name_col": None,
        "email_col": None,
        "valid": None,
        "report": None,
        "data_sig": None,
        "count": 1,
        "templates": {
            1: None,
            2: None
        },
        "styles": {
            1: DEFAULT_STYLE.copy(),
            2: DEFAULT_STYLE.copy()
        },
        "ttfs": {
            1: None,
            2: None
        },
        "font_confirm": None,
        "records": [],
        "generated_sig": None,
        "send_results": None,
        "send_sig": None,
        "subject": "Your certificate(s)",
        "body": (
            "Dear {{Name}},\n\n"
            "Please find your certificate(s) "
            "attached.\n\n"
            "Best regards,\n"
            "Organizing Team"
        )
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize()
s = st.session_state


# ==================================================
# SIGNATURES AND INVALIDATION
# ==================================================

def hash_value(value):
    if isinstance(value, bytes):
        return hashlib.sha256(value).hexdigest()

    encoded = json.dumps(
        value,
        sort_keys=True,
        default=str
    ).encode()

    return hashlib.sha256(encoded).hexdigest()


def invalidate_generation():
    s.records = []
    s.generated_sig = None
    s.send_results = None
    s.send_sig = None


def invalidate_design():
    s.font_confirm = None
    invalidate_generation()


def data_signature():
    return hash_value([
        hash_value(s.source_bytes)
        if s.source_bytes else None,
        s.name_col,
        s.email_col
    ])


def design_signature():
    return hash_value(
        [s.count] + [
            hash_value(s.templates[i])
            if s.templates[i] else None
            for i in range(1, s.count + 1)
        ]
    )


def font_signature():
    return hash_value(
        [design_signature()] + [
            {
                "style": s.styles[i],
                "ttf": (
                    hash_value(s.ttfs[i])
                    if s.ttfs[i] else None
                )
            }
            for i in range(1, s.count + 1)
        ]
    )


def generation_signature():
    return hash_value([
        data_signature(),
        font_signature()
    ])


# ==================================================
# PROGRESS TRACKING
# ==================================================

def progress_flags():
    upload = (
        s.df is not None
        and not s.df.empty
    )

    data = (
        upload
        and s.valid is not None
        and not s.valid.empty
        and s.data_sig == data_signature()
    )

    design = all(
        s.templates[i] is not None
        for i in range(1, s.count + 1)
    )

    font = (
        design
        and s.font_confirm == font_signature()
    )

    preview = (
        font
        and s.generated_sig == generation_signature()
        and bool(s.records)
        and all(
            len(record["files"]) == s.count
            for record in s.records
        )
    )

    email = (
        preview
        and s.send_results is not None
        and len(s.send_results) == len(s.records)
        and all(
            item["Status"] != "Not attempted"
            for item in s.send_results
        )
    )

    return [
        upload,
        data,
        design,
        font,
        preview,
        email
    ]


def navigate(target):
    if target > 0:
        if not all(progress_flags()[:target]):
            st.warning(
                "Complete the previous steps first."
            )
            return

    s.page = target
    st.rerun()


def navigation():
    st.divider()

    left, middle, right = st.columns([1, 3, 1])

    with left:
        if s.page > 0:
            if st.button(
                "← Previous",
                use_container_width=True
            ):
                navigate(s.page - 1)

    with middle:
        st.caption(
            f"Step {s.page + 1} of 6"
        )

    with right:
        if s.page < 5:
            if st.button(
                "Next →",
                type="primary",
                use_container_width=True
            ):
                navigate(s.page + 1)


# ==================================================
# FILE UPLOAD HELPERS
# ==================================================

def load_source():
    raw = s.source_bytes

    if not raw:
        return None

    if s.source_name.lower().endswith(".csv"):
        return pd.read_csv(
            BytesIO(raw),
            dtype=str,
            keep_default_na=False
        ).fillna("")

    return pd.read_excel(
        BytesIO(raw),
        dtype=str,
        keep_default_na=False
    ).fillna("")


def uploaded_source():
    uploaded = s.get("source_widget")

    if not uploaded:
        return

    if (
        s.source_bytes != uploaded.getvalue()
        or s.source_name != uploaded.name
    ):
        s.source_bytes = uploaded.getvalue()
        s.source_name = uploaded.name
        s.df = None
        s.valid = None
        s.report = None
        s.data_sig = None

        invalidate_generation()


def save_template(number):
    uploaded = s.get(
        f"template_widget_{number}"
    )

    if not uploaded:
        return

    raw = uploaded.getvalue()

    try:
        image = Image.open(BytesIO(raw))
        image.verify()
    except Exception:
        return

    if s.templates[number] != raw:
        s.templates[number] = raw
        invalidate_design()


def save_ttf(number):
    uploaded = s.get(
        f"ttf_widget_{number}"
    )

    if uploaded:
        if s.ttfs[number] != uploaded.getvalue():
            s.ttfs[number] = uploaded.getvalue()
            invalidate_design()


def replace_tokens(template, person):
    return re.sub(
        r"\{\{\s*(Name|Email)\s*\}\}",
        lambda match: str(
            person[match.group(1)]
        ),
        template
    )


def clean_filename(name):
    return (
        re.sub(
            r"[^a-zA-Z0-9_-]+",
            "_",
            name
        ).strip("_")[:45]
        or "Participant"
    )


# ==================================================
# HEADER
# ==================================================

st.markdown(
    """
    <div class="mirae">
        <h2>✦ MiraeTech</h2>
        <p>
            Certificate Automation Workspace
            · V3.3 Processing Feedback
        </p>
    </div>
    """,
    unsafe_allow_html=True
)

flags = progress_flags()

st.progress(
    sum(flags) / 6,
    text=f"{sum(flags)} of 6 steps complete"
)

columns = st.columns(6)

for index, column in enumerate(columns):
    with column:
        label = (
            ("✓ " if flags[index] else f"{index + 1}. ")
            + STEPS[index]
        )

        if st.button(
            label,
            key=f"topnav_{index}",
            type=(
                "primary"
                if s.page == index
                else "secondary"
            ),
            use_container_width=True
        ):
            navigate(index)

st.divider()


# ==================================================
# PAGE 1: UPLOAD
# ==================================================

if s.page == 0:
    st.header("1 · Upload participants")

    st.file_uploader(
        "CSV or Excel spreadsheet",
        type=["csv", "xlsx"],
        key="source_widget",
        on_change=uploaded_source
    )

    if s.source_bytes:
        try:
            with st.spinner(
                "Reading and preparing spreadsheet...",
                show_time=True
            ):
                s.df = load_source()

            if s.df.empty:
                st.error("The spreadsheet is empty.")

            else:
                st.success(
                    f"{len(s.df)} records loaded successfully."
                )

                st.dataframe(
                    s.df.head(10),
                    hide_index=True,
                    use_container_width=True
                )

        except Exception as error:
            s.df = None
            st.error(
                f"Could not read file: {error}"
            )

    navigation()


# ==================================================
# PAGE 2: DATA VALIDATION
# ==================================================

elif s.page == 1:
    st.header("2 · Validate data")

    if s.df is None:
        st.warning(
            "Upload a spreadsheet first."
        )

    else:
        names = list(s.df.columns)

        def suggest(words):
            for column in names:
                if column.lower().strip() in words:
                    return column
            return None

        options = [None] + names

        col1, col2 = st.columns(2)

        with col1:
            default_name = (
                s.name_col
                if s.name_col in names
                else suggest([
                    "name",
                    "full name",
                    "participant name"
                ])
            )

            name_column = st.selectbox(
                "Name column",
                options,
                index=options.index(default_name)
            )

        with col2:
            default_email = (
                s.email_col
                if s.email_col in names
                else suggest([
                    "email",
                    "email address"
                ])
            )

            email_column = st.selectbox(
                "Email column",
                options,
                index=options.index(default_email)
            )

        if (
            name_column != s.name_col
            or email_column != s.email_col
        ):
            s.name_col = name_column
            s.email_col = email_column
            s.valid = None
            s.report = None
            s.data_sig = None

            invalidate_generation()

        if st.button(
            "Validate student data",
            type="primary"
        ):
            if (
                not name_column
                or not email_column
                or name_column == email_column
            ):
                st.error(
                    "Select different Name and Email columns."
                )

            else:
                with st.status(
                    "Validating student records...",
                    expanded=True
                ) as status:

                    st.write(
                        "Reading participant names and email addresses..."
                    )

                    frame = pd.DataFrame({
                        "Name": (
                            s.df[name_column]
                            .astype(str)
                            .str.strip()
                        ),
                        "Email": (
                            s.df[email_column]
                            .astype(str)
                            .str.strip()
                        )
                    })

                    st.write(
                        "Checking missing names, invalid emails, "
                        "and duplicate addresses..."
                    )

                    duplicate = (
                        frame.Email
                        .str.lower()
                        .duplicated(keep=False)
                    )

                    issues = []

                    total = len(frame)

                    progress = st.progress(
                        0,
                        text="0% validated"
                    )

                    message = st.empty()

                    for position, (_, row) in enumerate(
                        frame.iterrows(),
                        start=1
                    ):
                        errors = []

                        if not row.Name:
                            errors.append("Missing name")

                        if not re.fullmatch(
                            r"[^@\s]+@[^@\s]+\.[^@\s]+",
                            row.Email
                        ):
                            errors.append("Invalid email")

                        if (
                            row.Email
                            and duplicate.iloc[position - 1]
                        ):
                            errors.append("Duplicate email")

                        issues.append("; ".join(errors))

                        # Limit UI updates for performance.
                        update_every = max(
                            1,
                            total // 100
                        )

                        if (
                            position % update_every == 0
                            or position == total
                        ):
                            progress.progress(
                                position / total,
                                text=(
                                    f"Validating {position} "
                                    f"of {total} records"
                                )
                            )

                            message.caption(
                                f"{position}/{total} student records checked"
                            )

                    report = frame.copy()

                    report.insert(
                        0,
                        "Row",
                        range(2, len(frame) + 2)
                    )

                    report["Issues"] = issues

                    s.report = report

                    s.valid = frame.loc[
                        [not issue for issue in issues]
                    ].copy()

                    s.data_sig = data_signature()

                    progress.progress(
                        1.0,
                        text="Validation complete"
                    )

                    status.update(
                        label="Student validation completed",
                        state="complete",
                        expanded=False
                    )

                st.success(
                    f"Validation finished: "
                    f"{len(s.valid)} valid records."
                )

        if s.report is not None:
            a, b = st.columns(2)

            a.metric("Valid", len(s.valid))

            b.metric(
                "Invalid",
                len(s.report) - len(s.valid)
            )

            st.dataframe(
                s.report,
                hide_index=True,
                use_container_width=True
            )

            if any(s.report.Issues):
                st.download_button(
                    "Download error report",
                    s.report.to_csv(index=False),
                    "validation_report.csv"
                )

    navigation()


# ==================================================
# PAGE 3: DESIGN
# ==================================================

elif s.page == 2:
    st.header("3 · Certificate design")

    count = st.radio(
        "Certificates per participant",
        [1, 2],
        index=s.count - 1,
        horizontal=True
    )

    if count != s.count:
        s.count = count
        invalidate_design()

    for number in range(1, s.count + 1):
        st.subheader(
            f"Certificate {number}"
        )

        st.file_uploader(
            f"Upload background image for certificate {number}",
            type=["png", "jpg", "jpeg"],
            key=f"template_widget_{number}",
            on_change=save_template,
            args=(number,)
        )

        if s.templates[number]:
            st.image(
                s.templates[number],
                width=550
            )

            st.success(
                "Template uploaded successfully."
            )

    navigation()


# ==================================================
# PAGE 4: LIVE FONT EDITOR
# ==================================================

elif s.page == 3:
    st.header("4 · Live font editor")

    st.info(
        "Drag sliders to see instant changes. "
        "Settings save when you release the slider."
    )

    for number in range(1, s.count + 1):
        st.subheader(
            f"Certificate {number}"
        )

        if not s.templates[number]:
            st.warning(
                "Upload a background on the Design step."
            )
            continue

        st.file_uploader(
            "Optional: upload your own TrueType font (.ttf)",
            type=["ttf"],
            key=f"ttf_widget_{number}",
            on_change=save_ttf,
            args=(number,)
        )

        if s.ttfs[number]:
            st.caption(
                "The uploaded font overrides the gallery "
                "font in generated PDFs."
            )

            if st.button(
                "Remove uploaded font",
                key=f"remove_ttf_{number}"
            ):
                s.ttfs[number] = None
                invalidate_design()
                st.rerun()

        with st.spinner(
            "Preparing certificate editor...",
            show_time=True
        ):
            image = Image.open(
                BytesIO(s.templates[number])
            ).convert("RGB")

            image.thumbnail((1500, 1100))

            buffer = BytesIO()
            image.save(buffer, format="PNG")

            background_b64 = base64.b64encode(
                buffer.getvalue()
            ).decode()

        new_settings = EDITOR(
            background=background_b64,
            settings=s.styles[number],
            sample="Sample Participant",
            key=f"editor_{number}",
            default=None
        )

        if isinstance(new_settings, dict):
            clean = {
                key: new_settings.get(
                    key,
                    s.styles[number][key]
                )
                for key in DEFAULT_STYLE
            }

            if clean != s.styles[number]:
                s.styles[number] = clean
                invalidate_design()

        st.caption(
            f"Selected: {s.styles[number]['font']} · "
            f"{s.styles[number]['size']} pt · "
            f"X {s.styles[number]['x']}% · "
            f"Y {s.styles[number]['y']}%"
        )

        with st.spinner(
            "Preparing sample PDF...",
            show_time=True
        ):
            try:
                sample_pdf = create_certificate(
                    "Sample Participant",
                    s.templates[number],
                    s.styles[number],
                    s.ttfs[number]
                )

                st.download_button(
                    f"Download Certificate {number} Sample PDF",
                    data=sample_pdf,
                    file_name=f"certificate_{number}_sample.pdf",
                    mime="application/pdf",
                    key=f"sample_pdf_{number}"
                )

            except Exception as error:
                st.error(
                    f"Font/PDF error: {error}"
                )

        st.divider()

    if st.button(
        "Confirm font settings",
        type="primary"
    ):
        with st.status(
            "Checking fonts and certificate settings...",
            expanded=True
        ) as status:

            try:
                for number in range(1, s.count + 1):
                    st.write(
                        f"Checking certificate {number}..."
                    )

                    create_certificate(
                        "Sample Participant",
                        s.templates[number],
                        s.styles[number],
                        s.ttfs[number]
                    )

                s.font_confirm = font_signature()

                status.update(
                    label="Font settings verified",
                    state="complete",
                    expanded=False
                )

                st.success(
                    "Font settings confirmed."
                )

            except Exception as error:
                status.update(
                    label="Font verification failed",
                    state="error",
                    expanded=True
                )

                st.error(
                    f"Cannot confirm font: {error}"
                )

    if progress_flags()[3]:
        st.success(
            "Fonts confirmed. Continue to Preview."
        )

    navigation()


# ==================================================
# PAGE 5: GENERATE CERTIFICATES
# ==================================================

elif s.page == 4:
    st.header("5 · Generate certificates")

    if not all(progress_flags()[:4]):
        st.warning(
            "Finish the previous steps."
        )

    else:
        st.write(
            f"{len(s.valid)} participants · "
            f"{s.count} certificate(s) each"
        )

        if st.button(
            "Generate PDF certificates",
            type="primary"
        ):
            with st.status(
                "Generating certificates...",
                expanded=True
            ) as status:

                st.write(
                    "Preparing certificate templates and fonts..."
                )

                records = []

                total = len(s.valid)

                bar = st.progress(
                    0,
                    text="Starting generation..."
                )

                current = st.empty()

                success_count = 0
                failed_count = 0

                for position, (_, person) in enumerate(
                    s.valid.iterrows(),
                    start=1
                ):
                    person = person.to_dict()

                    files = []
                    error = ""

                    current.info(
                        f"Processing: {person['Name']}"
                    )

                    try:
                        for number in range(
                            1,
                            s.count + 1
                        ):
                            pdf = create_certificate(
                                person["Name"],
                                s.templates[number],
                                s.styles[number],
                                s.ttfs[number]
                            )

                            filename = (
                                f"{position:04d}_"
                                f"{clean_filename(person['Name'])}_"
                                f"Certificate_{number}.pdf"
                            )

                            files.append(
                                (filename, pdf)
                            )

                        success_count += 1

                    except Exception as exception:
                        files = []
                        error = str(exception)
                        failed_count += 1

                    records.append({
                        "person": person,
                        "files": files,
                        "error": error
                    })

                    bar.progress(
                        position / total,
                        text=(
                            f"Generated {position} of {total} "
                            f"participants"
                        )
                    )

                s.records = records

                s.generated_sig = generation_signature()

                s.send_results = None
                s.send_sig = None

                current.empty()

                status.update(
                    label="Certificate generation finished",
                    state=(
                        "complete"
                        if failed_count == 0
                        else "error"
                    ),
                    expanded=False
                )

            if failed_count == 0:
                st.success(
                    f"Successfully generated certificates "
                    f"for all {success_count} participants."
                )

            else:
                st.warning(
                    f"{success_count} participants completed; "
                    f"{failed_count} failed."
                )

        if s.records:
            failed = [
                record
                for record in s.records
                if len(record["files"]) != s.count
            ]

            good = [
                record
                for record in s.records
                if len(record["files"]) == s.count
            ]

            if failed:
                st.error(
                    f"{len(failed)} participant(s) failed."
                )

                st.dataframe(
                    pd.DataFrame([
                        {
                            "Name": record["person"]["Name"],
                            "Error": record["error"]
                        }
                        for record in failed
                    ]),
                    hide_index=True
                )

            if good:
                with st.spinner(
                    "Preparing ZIP download...",
                    show_time=True
                ):
                    zip_buffer = BytesIO()

                    with ZipFile(
                        zip_buffer,
                        "w",
                        ZIP_DEFLATED
                    ) as archive:
                        for record in good:
                            for filename, pdf in record["files"]:
                                archive.writestr(
                                    filename,
                                    pdf
                                )

                st.download_button(
                    "Download all certificates (ZIP)",
                    zip_buffer.getvalue(),
                    "miraetech_certificates.zip",
                    "application/zip",
                    type="primary"
                )

                selected = st.selectbox(
                    "Participant",
                    range(len(good)),
                    format_func=lambda index: (
                        good[index]["person"]["Name"]
                    )
                )

                for filename, pdf in good[selected]["files"]:
                    st.download_button(
                        f"Download {filename}",
                        pdf,
                        filename,
                        "application/pdf",
                        key=filename
                    )

    navigation()


# ==================================================
# PAGE 6: EMAIL DELIVERY
# ==================================================

elif s.page == 5:
    st.header("6 · Email delivery")

    if not progress_flags()[4]:
        st.warning(
            "Generate all certificates successfully first."
        )

    else:
        subject = st.text_input(
            "Email subject",
            key="subject"
        )

        body = st.text_area(
            "Email body",
            key="body",
            height=170
        )

        st.caption(
            "Use {{Name}} and {{Email}} "
            "to personalize your email."
        )

        selected = st.selectbox(
            "Preview recipient",
            range(len(s.records)),
            format_func=lambda index: (
                s.records[index]["person"]["Name"]
            )
        )

        person = s.records[selected]["person"]

        st.write(
            "**To:**",
            person["Email"]
        )

        st.write(
            "**Subject:**",
            replace_tokens(subject, person)
        )

        st.text(
            replace_tokens(body, person)
        )

        st.write(
            "**Attachments:**",
            len(s.records[selected]["files"])
        )

        sender = st.text_input(
            "Sender Gmail address"
        ).strip()

        password = st.text_input(
            "Gmail App Password",
            type="password"
        ).replace(" ", "")

        signature = hash_value([
            s.generated_sig,
            subject,
            body,
            sender
        ])

        if s.send_sig != signature:
            s.send_sig = signature
            s.send_results = None

        if s.send_results is not None:
            st.warning(
                "This batch was already attempted "
                "in this session. Check Gmail Sent "
                "before retrying."
            )

        consent = st.checkbox(
            "I verified all recipients and "
            "authorize sending these emails."
        )

        unknown = set(
            re.findall(
                r"\{\{\s*([^{}]+?)\s*\}\}",
                subject + "\n" + body
            )
        ) - {"Name", "Email"}

        if unknown:
            st.error(
                f"Unknown placeholders: {sorted(unknown)}"
            )

        valid_sender = bool(
            re.fullmatch(
                r"[^@\s]+@[^@\s]+\.[^@\s]+",
                sender
            )
        )

        ready = (
            consent
            and valid_sender
            and len(password) == 16
            and bool(subject.strip())
            and bool(body.strip())
            and not unknown
            and "\n" not in subject
            and "\r" not in subject
            and s.send_results is None
        )

        if st.button(
            "Send certificates",
            type="primary",
            disabled=not ready
        ):
            with st.status(
                "Sending certificate emails...",
                expanded=True
            ) as status:

                total = len(s.records)

                s.send_results = [
                    {
                        "Name": record["person"]["Name"],
                        "Email": record["person"]["Email"],
                        "Status": "Not attempted"
                    }
                    for record in s.records
                ]

                bar = st.progress(
                    0,
                    text="Starting email delivery..."
                )

                current = st.empty()

                accepted_count = 0
                failed_count = 0

                for index, record in enumerate(
                    s.records
                ):
                    recipient = record["person"]["Email"]

                    current.info(
                        f"Sending to: {recipient}"
                    )

                    s.send_results[index]["Status"] = (
                        "Attempted — check Gmail Sent"
                    )

                    try:
                        send_certificate(
                            sender,
                            password,
                            recipient,
                            replace_tokens(
                                subject,
                                record["person"]
                            ),
                            replace_tokens(
                                body,
                                record["person"]
                            ),
                            record["files"]
                        )

                        s.send_results[index]["Status"] = (
                            "Accepted by Gmail"
                        )

                        accepted_count += 1

                    except Exception as error:
                        failed_count += 1

                        st.warning(
                            f"{recipient}: {error}"
                        )

                    bar.progress(
                        (index + 1) / total,
                        text=(
                            f"Processed {index + 1} "
                            f"of {total} emails"
                        )
                    )

                current.empty()

                status.update(
                    label="Email processing finished",
                    state=(
                        "complete"
                        if failed_count == 0
                        else "error"
                    ),
                    expanded=False
                )

            if failed_count == 0:
                st.success(
                    f"All {accepted_count} emails were "
                    f"accepted by Gmail."
                )

            else:
                st.warning(
                    f"{accepted_count} accepted by Gmail; "
                    f"{failed_count} encountered errors."
                )

        if s.send_results is not None:
            report = pd.DataFrame(
                s.send_results
            )

            st.dataframe(
                report,
                hide_index=True,
                use_container_width=True
            )

            st.download_button(
                "Download sending report",
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

    navigation()
