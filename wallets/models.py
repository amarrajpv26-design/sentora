# wallets/models.py
from django.db import models
from django.conf import settings


class Wallet(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet"
    )
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Wallet - ₹{self.balance}"


class WalletTransaction(models.Model):
    TRANSACTION_TYPE = (
        ("CREDIT", "Credit (Money In)"),
        ("DEBIT", "Debit (Money Out)"),
    )

    TRANSACTION_PURPOSE = (
        ("REFUND", "Refund for Cancellation/Return"),
        ("PURCHASE", "Order Payment"),
        ("RECHARGE", "Wallet Recharge"),
        ("ADMIN_ADJUST", "Admin Adjustment"),
    )

    wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name="transactions"
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE)
    purpose = models.CharField(max_length=20, choices=TRANSACTION_PURPOSE)
    razorpay_payment_id = models.CharField(
        max_length=100, unique=True, null=True, blank=True
    )
    # Optional: Link directly to an order for clean tracking history
    order_id = models.CharField(max_length=50, blank=True, null=True)

    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.transaction_type} - ₹{self.amount} ({self.purpose})"
