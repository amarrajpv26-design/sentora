from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import datetime
from allauth.socialaccount.signals import social_account_added
from django.dispatch import receiver


@receiver(social_account_added)
def linked_social_account(request, sociallogin, **kwargs):
    user = sociallogin.user
    user.is_verified = True
    user.is_active = True
    user.save()


class User(AbstractUser):
    # users/models.py
    username = models.CharField(max_length=150, unique=True, blank=False, null=False)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    dob = models.DateField(null=True, blank=True)
    profile_image = models.ImageField(upload_to="profiles/", null=True, blank=True)
    is_blocked = models.BooleanField(default=False)

    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    # users/models.py — add inside the User class
    referred_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="referrals_made",
        help_text="The user whose referral code/link was used at signup.",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email

    def is_otp_expired(self):
        if not self.otp_created_at:
            return True
        return timezone.now() > self.otp_created_at + datetime.timedelta(minutes=1)


class Address(models.Model):
    ADDRESS_TYPES = (
        ("HOME", "Home"),
        ("WORK", "Work"),
        ("OTHER", "Other"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="addresses")
    full_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    address_type = models.CharField(
        max_length=10, choices=ADDRESS_TYPES, default="HOME"
    )
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not Address.objects.filter(user=self.user).exclude(pk=self.pk).exists():
            self.is_default = True
        elif self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(
                pk=self.pk
            ).update(is_default=False)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.address_type}) - {self.city}"
