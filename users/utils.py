import random
import string
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings


def generate_otp():
    return "".join(random.choices(string.digits, k=6))


def send_otp_email(user_email, otp):
    subject = "Scentora | Verify Your Identity"
    from_email = settings.DEFAULT_FROM_EMAIL

    context = {"otp": otp, "email": user_email}
    html_content = render_to_string('email/otp_email.html', context)

    text_content = strip_tags(html_content)

    msg = EmailMultiAlternatives(subject, text_content, from_email, [user_email])

    msg.attach_alternative(html_content, "text/html")

    msg.send()
