
import smtplib
from email.message import EmailMessage


def send_certificate(
    sender,
    app_password,
    recipient,
    subject,
    body,
    attachments,
):
    sender = sender.strip()
    recipient = recipient.strip()
    app_password = app_password.replace(" ", "")

    if not sender or not recipient:
        raise ValueError(
            "Sender and recipient are required."
        )

    if not app_password:
        raise ValueError(
            "Gmail App Password is required."
        )

    if not attachments:
        raise ValueError(
            "No certificate attachments provided."
        )

    message = EmailMessage()

    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    for filename, pdf_bytes in attachments:
        if not isinstance(pdf_bytes, bytes):
            raise TypeError("PDF must be bytes.")

        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError(
                f"Invalid PDF: {filename}"
            )

        message.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=filename
        )

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
        timeout=30
    ) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(message)

    return True
