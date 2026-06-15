from django.db import models
from django.conf import settings
from products.models import Product
from orders.models import OrderItem


class Review(models.Model):
    RATING_CHOICES = [(i, i) for i in range(1, 6)]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reviews')
    order_item = models.OneToOneField(OrderItem, on_delete=models.CASCADE, related_name='review')

    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)
    title = models.CharField(max_length=150, blank=True)
    comment = models.TextField()

    is_approved = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} — {self.product.name} ({self.rating}★)"