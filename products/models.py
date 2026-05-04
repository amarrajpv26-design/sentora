from django.db import models
from django.utils.text import slugify
from django.core.exceptions import ValidationError

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
