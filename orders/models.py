from django.db import models
from django.conf import settings
from products.models import ProductVariant


class Order(models.Model):

    ORDER_STATUS = (
        ("PENDING", "Pending"),
        ("CONFIRMED", "Confirmed"),
        ("SHIPPED", "Shipped"),
        ("DELIVERED", "Delivered"),
        ("CANCELLED", "Cancelled"),
        ("RETURN_REQUESTED", "Return Requested"),
        ("RETURNED", "Returned"),
    )

    PAYMENT_STATUS = (
        ("PENDING", "Pending"),
        ("PAID", "Paid"),
        ("FAILED", "Failed"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    order_id = models.CharField(max_length=50, unique=True)

    address = models.ForeignKey("users.Address", on_delete=models.SET_NULL, null=True)

    # SNAPSHOT DATA
    full_name = models.CharField(max_length=200)
    phone_number = models.CharField(max_length=20)

    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True, null=True)

    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=20)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    shipping_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    payment_method = models.CharField(max_length=50)

    payment_status = models.CharField(
        max_length=20, choices=PAYMENT_STATUS, default="PENDING"
    )

    order_status = models.CharField(
        max_length=30, choices=ORDER_STATUS, default="PENDING"
    )

    cancellation_reason = models.TextField(blank=True, null=True)

    return_reason = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:

        ordering = ["-created_at"]

    def __str__(self):

        return self.order_id


class OrderItem(models.Model):

    ITEM_STATUS = (
        ("ACTIVE", "Active"),
        ("CANCELLED", "Cancelled"),
        ("RETURNED", "Returned"),
    )

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")

    product_variant = models.ForeignKey(
        ProductVariant, on_delete=models.SET_NULL, null=True
    )

    product_name = models.CharField(max_length=255)

    quantity = models.PositiveIntegerField()

    price = models.DecimalField(max_digits=10, decimal_places=2)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    item_status = models.CharField(max_length=20, choices=ITEM_STATUS, default="ACTIVE")

    cancellation_reason = models.TextField(blank=True, null=True)

    return_reason = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):

        return self.product_name
