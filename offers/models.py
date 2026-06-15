from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from products.models import Product, ProductVariant, Category
import uuid


class OfferBase(models.Model):
    """Abstract base for all offer types."""

    DISCOUNT_TYPE_CHOICES = [
        ("PERCENTAGE", "Percentage (%)"),
        ("FIXED", "Fixed Amount (₹)"),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    discount_type = models.CharField(
        max_length=20, choices=DISCOUNT_TYPE_CHOICES, default="PERCENTAGE"
    )
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Percentage (0–100) or fixed ₹ amount",
    )
    is_active = models.BooleanField(default=True)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def is_live(self):
        now = timezone.now()
        return self.is_active and self.start_date <= now <= self.end_date

    def clean(self):
        if self.discount_type == "PERCENTAGE":
            if not (0 < self.discount_value <= 100):
                raise ValidationError("Percentage discount must be between 1 and 100.")
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError("End date must be after start date.")

    def compute_discount(self, original_price):
        """Return the discounted price given the original price."""
        from decimal import Decimal

        if not self.is_live():
            return original_price
        if self.discount_type == "PERCENTAGE":
            discount = (original_price * self.discount_value) / Decimal("100")
        else:
            discount = self.discount_value
        discounted = original_price - discount
        return max(discounted, Decimal("0.00"))

    def __str__(self):
        return self.name


class ProductOffer(OfferBase):
    """Offer applied to a specific product (all its variants)."""

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="offers",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Product Offer"

    def __str__(self):
        return f"{self.name} → {self.product.name}"


class CategoryOffer(OfferBase):
    """Offer applied to all products in a category."""

    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="offers",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Category Offer"

    def __str__(self):
        return f"{self.name} → {self.category.name}"


class ReferralOffer(models.Model):
    """
    Referral offer system.
    Supports two approaches:
      1. Token URL  — a unique UUID link shared by the referrer.
         e.g. /ref/<token>/
         When a new user signs up via this URL they get a wallet credit.
      2. Referral Code — a short human-readable code the user can share.
         e.g. AMAR50
    Both are stored on this model; each user has at most one ReferralOffer.
    """

    REWARD_TYPE_CHOICES = [
        ("WALLET_CREDIT", "Wallet Credit (₹)"),
        ("PERCENTAGE", "Percentage Discount (%)"),
    ]

    referrer = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="referral_offer",
    )

    # Token URL approach
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # Human-readable code approach
    referral_code = models.CharField(max_length=20, unique=True, blank=True)

    # Reward settings
    referrer_reward_type = models.CharField(
        max_length=20,
        choices=REWARD_TYPE_CHOICES,
        default="WALLET_CREDIT",
        help_text="Reward given to the person who referred.",
    )
    referrer_reward_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=100,
        help_text="₹ credit or % discount for the referrer.",
    )
    referee_reward_type = models.CharField(
        max_length=20,
        choices=REWARD_TYPE_CHOICES,
        default="WALLET_CREDIT",
        help_text="Reward given to the new user who signed up.",
    )
    referee_reward_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=50,
        help_text="₹ credit or % discount for the referee.",
    )

    is_active = models.BooleanField(default=True)
    max_uses = models.PositiveIntegerField(
        default=0, help_text="0 = unlimited"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Referral Offer"

    def save(self, *args, **kwargs):
        if not self.referral_code:
            base = self.referrer.username.upper()[:6]
            suffix = uuid.uuid4().hex[:4].upper()
            self.referral_code = f"{base}{suffix}"
        super().save(*args, **kwargs)

    @property
    def use_count(self):
        return self.usages.filter(reward_granted=True).count()

    @property
    def is_exhausted(self):
        if self.max_uses == 0:
            return False
        return self.use_count >= self.max_uses

    def __str__(self):
        return f"Referral by {self.referrer.username} [{self.referral_code}]"


class ReferralUsage(models.Model):
    """Records every time someone signs up via a referral."""

    referral_offer = models.ForeignKey(
        ReferralOffer, on_delete=models.CASCADE, related_name="usages"
    )
    referee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="referral_usages",
    )
    reward_granted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("referral_offer", "referee")

    def __str__(self):
        return f"{self.referee.username} via {self.referral_offer.referral_code}"