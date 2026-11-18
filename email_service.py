
import smtplib
from email.message import EmailMessage


def send_certificate(
    sender,
    app_password,
    recipient,
    subject,
    body,
    attachments
):
    message = EmailMessage()

    message["From"] = sender.strip()
    message["To"] = recipient.strip()
    message["Subject"] = subject

    message.set_content(body)

    for filename, pdf in attachments:
        if not pdf.startswith(b"%PDF"):
            raise ValueError(
                f"Invalid PDF attachment: {filename}"
            )

        message.add_attachment(
            pdf,
            maintype="application",
            subtype="pdf",
            filename=filename
        )

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
        timeout=30
    ) as smtp:

        smtp.login(
            sender.strip(),
            app_password.replace(" ", "")
        )

        smtp.send_message(message)
