import random
import string
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone


def generate_otp():
    return "".join(random.choices(string.digits, k=6))


def send_otp_email(user_email, otp):
    subject = "Verify Your Scentora Account"
    message = f"Your verification code is: {otp}. This code expires in 2 minutes."
    email_from = settings.DEFAULT_FROM_EMAIL
    recipient_list = [user_email]

    send_mail(subject, message, email_from, recipient_list)
