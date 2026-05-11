from django.db import models
from django.utils.text import slugify
from django.core.exceptions import ValidationError
import uuid


class Category(models.Model):
    # Core Information
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    category_image = models.ImageField(
        upload_to="category_images/", null=True, blank=True
    )

    # Management Toggles
    is_active = models.BooleanField(
        default=True, help_text="Uncheck to soft-delete/hide category from everywhere."
    )
    show_in_nav = models.BooleanField(
        default=True, help_text="Should this appear in the main website menu?"
    )
    is_featured = models.BooleanField(
        default=False, help_text="Should this show up on the homepage sections?"
    )

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Requirement: Sort descending
        ordering = ["-created_at"]
        verbose_name_plural = "Categories"

    def clean(self):
        # This checks if 'men', 'MEN', or 'Men' already exists in the database
        if Category.objects.filter(name__iexact=self.name).exclude(pk=self.pk).exists():
            raise ValidationError(
                f"A vault named '{self.name}' already exists (names are case-insensitive)."
            )

    def save(self, *args, **kwargs):
        # This line is CRITICAL: it forces the clean() method to run before every save
        self.full_clean()
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Brand(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    logo = models.ImageField(upload_to="brand_logos/", null=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(models.Model):
    # Core Identity
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name="products")
    # Relationships
    # Many-to-Many because a perfume can be 'Men', 'Winter Noir', and 'Limited Edition'
    categories = models.ManyToManyField(Category, related_name="products")

    # Scent Profile (The Luxury Specs)
    top_notes = models.CharField(max_length=255, help_text="e.g., Bergamot, Lemon")
    heart_notes = models.CharField(max_length=255, help_text="e.g., Jasmine, Rose")
    base_notes = models.CharField(max_length=255, help_text="e.g., Amber, Musk, Oud")

    # Management
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ProductVariant(models.Model):
    # Linking to the Parent Product
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="variants"
    )

    # Variant Specifics (Option B: Unique Price per Size)
    size = models.CharField(max_length=50, help_text="e.g., 50ml, 100ml, Sample")
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price in ₹")
    offer_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Sale price in ₹",
    )
    stock = models.PositiveIntegerField(default=0)
    sku = models.CharField(max_length=50, unique=True, blank=True)

    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.sku:
            # Auto-generate a unique SKU if not provided
            self.sku = f"SCENT-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.product.name} - {self.size}"

    def get_price(self):
        if self.offer_price and self.offer_price < self.price:
            return self.offer_price
        return self.price


class ProductImage(models.Model):
    # Linking to the Parent Product
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images"
    )

    # Image logic (We will use the 3:4 crop logic here)
    image = models.ImageField(upload_to="product_images/")
    is_main = models.BooleanField(
        default=False, help_text="The first image the user sees."
    )

    def __str__(self):
        return f"Image for {self.product.name}"
