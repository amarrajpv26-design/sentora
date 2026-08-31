import re
from django import forms
from .models import Category, Product

MONTH_CHOICES = [
    (1, "January"),
    (2, "February"),
    (3, "March"),
    (4, "April"),
    (5, "May"),
    (6, "June"),
    (7, "July"),
    (8, "August"),
    (9, "September"),
    (10, "October"),
    (11, "November"),
    (12, "December"),
]

DAY_CHOICES = [(i, str(i)) for i in range(1, 32)]


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = [
            "name",
            "description",
            "category_image",
            "is_active",
            "is_featured",
            "is_seasonal",
            "season_start_month",
            "season_start_day",
            "season_end_month",
            "season_end_day",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "luxury-input py-4 px-6 rounded-2xl text-sm w-full font-bold tracking-tight",
                    "placeholder": "e.g., Midnight Oud",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "luxury-input py-4 px-6 rounded-2xl text-sm w-full font-medium",
                    "rows": 5,
                    "placeholder": "Describe the essence, notes, and character of this collection...",
                }
            ),
            "category_image": forms.FileInput(
                attrs={
                    "class": "text-[10px] text-white/20 file:bg-white/5 file:border-0 file:px-4 file:py-2 file:rounded-lg file:text-white/60 file:text-[9px] file:uppercase file:font-black file:tracking-[1px] hover:file:bg-white/10"
                }
            ),
            "season_start_month": forms.Select(
                choices=[("", "-- Month --")] + MONTH_CHOICES,
                attrs={
                    "class": "luxury-input py-3 px-4 rounded-xl text-xs w-full appearance-none",
                },
            ),
            "season_start_day": forms.Select(
                choices=[("", "-- Day --")] + DAY_CHOICES,
                attrs={
                    "class": "luxury-input py-3 px-4 rounded-xl text-xs w-full appearance-none",
                },
            ),
            "season_end_month": forms.Select(
                choices=[("", "-- Month --")] + MONTH_CHOICES,
                attrs={
                    "class": "luxury-input py-3 px-4 rounded-xl text-xs w-full appearance-none",
                },
            ),
            "season_end_day": forms.Select(
                choices=[("", "-- Day --")] + DAY_CHOICES,
                attrs={
                    "class": "luxury-input py-3 px-4 rounded-xl text-xs w-full appearance-none",
                },
            ),
        }
        def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()

        if len(name) < 2:
            raise forms.ValidationError("Category name must be at least 2 characters long.")
        if len(name) > 100:
            raise forms.ValidationError("Category name cannot exceed 100 characters.")
        if not re.match(r"^[A-Za-z0-9\s&'\-]+$", name):
            raise forms.ValidationError(
                "Category name contains invalid characters. Only letters, numbers, "
                "spaces, and & ' - are allowed."
            )
        return name
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        self.fields["description"].required = True
        # Seasonal date fields are optional at form level;
        # model.clean() enforces them only when is_seasonal=True
        for f in [
            "season_start_month",
            "season_start_day",
            "season_end_month",
            "season_end_day",
        ]:
            self.fields[f].required = False


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "categories",
            "description",
            "top_notes",
            "heart_notes",
            "base_notes",
            "is_featured",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "luxury-input py-4 px-6 rounded-xl text-sm w-full font-bold",
                    "placeholder": "e.g., Midnight Oud",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "luxury-input py-4 px-6 rounded-xl text-sm w-full",
                    "rows": 4,
                    "placeholder": "Describe the soul of this fragrance...",
                }
            ),
            "top_notes": forms.TextInput(
                attrs={"class": "luxury-input py-4 px-6 rounded-xl text-sm w-full"}
            ),
            "heart_notes": forms.TextInput(
                attrs={"class": "luxury-input py-4 px-6 rounded-xl text-sm w-full"}
            ),
            "base_notes": forms.TextInput(
                attrs={"class": "luxury-input py-4 px-6 rounded-xl text-sm w-full"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        self.fields["description"].required = True
        self.fields["categories"].required = True
        self.fields["categories"].widget = forms.CheckboxSelectMultiple()

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()

        if len(name) < 2:
            raise forms.ValidationError(
                "Product name must be at least 2 characters long."
            )
        if len(name) > 100:
            raise forms.ValidationError("Product name cannot exceed 100 characters.")
        if not re.match(r"^[A-Za-z0-9À-ÿ&'\-\.\s]+$", name):
            raise forms.ValidationError(
                "Product name contains invalid characters. Only letters, numbers, "
                "spaces, and & ' - . are allowed."
            )

        existing = Product.objects.filter(name__iexact=name)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError(f"A product named '{name}' already exists.")

        return name

    def clean_categories(self):
        categories = self.cleaned_data.get("categories")
        if not categories:
            raise forms.ValidationError("At least one category must be selected.")
        return categories