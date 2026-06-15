# coupons/models.py
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Coupon(models.Model):
    code = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=255, blank=True, default="")

    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()

    is_fixed = models.BooleanField(
        default=False,
        help_text="Check for a flat ₹ amount discount. Leave unchecked for a percentage discount.",
    )
    discount = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Percentage (1-100) for % coupons, or flat ₹ amount for fixed coupons.",
    )

    max_discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum discount this coupon can give. Required for percentage coupons.",
    )

    min_purchase = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    active = models.BooleanField(default=True)

    usage_limit = models.PositiveIntegerField(
        default=1,
        help_text="Total number of times this coupon can be used across all customers.",
    )
    usage_limit_per_user = models.PositiveIntegerField(
        default=1,
        help_text="Number of times a single customer can use this coupon.",
    )

    used_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Display / admin helpers
    # ------------------------------------------------------------------
    def get_status(self):
        """Returns one of: inactive, scheduled, expired, exhausted, active."""
        now = timezone.now()
        if not self.active:
            return "inactive"
        if now < self.valid_from:
            return "scheduled"
        if now > self.valid_to:
            return "expired"
        if self.usage_limit and self.used_count >= self.usage_limit:
            return "exhausted"
        return "active"

    @property
    def is_used(self):
        """True if this coupon has ever been applied to an order."""
        return self.usages.exists()

    # ------------------------------------------------------------------
    # Validation + discount calculation (used by checkout/cart flows)
    # ------------------------------------------------------------------
    def is_valid_for_user(self, user, cart_total):
        now = timezone.now()
        cart_total = Decimal(cart_total)

        if not self.active:
            return False, "This coupon is no longer active."

        if now < self.valid_from:
            return False, "This coupon is not active yet."

        if now > self.valid_to:
            return False, "This coupon has expired."

        if cart_total < self.min_purchase:
            return False, f"Add items worth ₹{self.min_purchase} or more to use this coupon."

        if self.usage_limit and self.used_count >= self.usage_limit:
            return False, "This coupon has reached its usage limit."

        if self.usage_limit_per_user and getattr(user, "is_authenticated", False):
            user_uses = self.usages.filter(user=user).count()
            if user_uses >= self.usage_limit_per_user:
                return False, "You have already used this coupon."

        return True, ""

    def calculate_discount(self, cart_total):
        """Returns the discount amount for the given cart total, capped sensibly."""
        cart_total = Decimal(cart_total)

        if self.is_fixed:
            discount_amount = Decimal(self.discount)
        else:
            discount_amount = (cart_total * Decimal(self.discount)) / Decimal("100")
            if self.max_discount_amount:
                discount_amount = min(discount_amount, self.max_discount_amount)

        # Never discount more than the cart itself
        discount_amount = min(discount_amount, cart_total)
        return discount_amount.quantize(Decimal("0.01"))


class CouponUsage(models.Model):
    """
    One row per (coupon, user, order) — the audit trail that powers
    per-user usage limits and the 'has this coupon ever been used'
    check used by the admin delete action.
    """

    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name="usages")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="coupon_usages",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coupon_usages",
    )
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-used_at"]

    def __str__(self):
        return f"{self.coupon.code} – {self.user} – {self.order_id or 'no order'}"