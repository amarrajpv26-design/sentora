import random
import string
from datetime import timedelta
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.conf import settings

# Single source of truth for every OTP flow (signup, email-change, new-email)
OTP_TTL_MINUTES = 2
RESEND_COOLDOWN_SECONDS = 60


def generate_otp():
    return "".join(random.choices(string.digits, k=6))


def send_otp_email(user_email, otp):
    subject = "Scentora | Verify Your Identity"
    from_email = settings.DEFAULT_FROM_EMAIL

    context = {"otp": otp, "email": user_email, "ttl_minutes": OTP_TTL_MINUTES}
    html_content = render_to_string('email/otp_email.html', context)

    text_content = strip_tags(html_content)

    msg = EmailMultiAlternatives(subject, text_content, from_email, [user_email])

    msg.attach_alternative(html_content, "text/html")

    msg.send()


def is_otp_expired(otp_created_at_str):
    """otp_created_at_str is the ISO string stored in the session when the OTP was issued/resent."""
    created_at = parse_datetime(otp_created_at_str)
    return timezone.now() > created_at + timedelta(minutes=OTP_TTL_MINUTES)


def get_resend_wait_seconds(otp_created_at_str):
    """
    Seconds remaining before the resend button should unlock.
    Computed fresh from the stored timestamp every time it's called, so a page
    reload shows the correct remaining time instead of resetting to 60.
    """
    created_at = parse_datetime(otp_created_at_str)
    elapsed = (timezone.now() - created_at).total_seconds()
    remaining = RESEND_COOLDOWN_SECONDS - int(elapsed)
    return max(0, remaining)