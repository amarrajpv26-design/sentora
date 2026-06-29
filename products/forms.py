from django import forms
from .models import Category


MONTH_CHOICES = [
    (1, 'January'), (2, 'February'), (3, 'March'),
    (4, 'April'),   (5, 'May'),      (6, 'June'),
    (7, 'July'),    (8, 'August'),   (9, 'September'),
    (10, 'October'),(11, 'November'),(12, 'December'),
]

DAY_CHOICES = [(i, str(i)) for i in range(1, 32)]


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = [
            'name', 'description', 'category_image',
            'is_active', 'is_featured',
            'is_seasonal',
            'season_start_month', 'season_start_day',
            'season_end_month',   'season_end_day',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'luxury-input py-4 px-6 rounded-2xl text-sm w-full font-bold tracking-tight',
                'placeholder': "e.g., Midnight Oud"
            }),
            'description': forms.Textarea(attrs={
                'class': 'luxury-input py-4 px-6 rounded-2xl text-sm w-full font-medium',
                'rows': 5,
                'placeholder': "Describe the essence, notes, and character of this collection..."
            }),
            'category_image': forms.FileInput(attrs={
                'class': 'text-[10px] text-white/20 file:bg-white/5 file:border-0 file:px-4 file:py-2 file:rounded-lg file:text-white/60 file:text-[9px] file:uppercase file:font-black file:tracking-[1px] hover:file:bg-white/10'
            }),
            'season_start_month': forms.Select(choices=[('', '-- Month --')] + MONTH_CHOICES, attrs={
                'class': 'luxury-input py-3 px-4 rounded-xl text-xs w-full appearance-none',
            }),
            'season_start_day': forms.Select(choices=[('', '-- Day --')] + DAY_CHOICES, attrs={
                'class': 'luxury-input py-3 px-4 rounded-xl text-xs w-full appearance-none',
            }),
            'season_end_month': forms.Select(choices=[('', '-- Month --')] + MONTH_CHOICES, attrs={
                'class': 'luxury-input py-3 px-4 rounded-xl text-xs w-full appearance-none',
            }),
            'season_end_day': forms.Select(choices=[('', '-- Day --')] + DAY_CHOICES, attrs={
                'class': 'luxury-input py-3 px-4 rounded-xl text-xs w-full appearance-none',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].required = True
        self.fields['description'].required = True
        # Seasonal date fields are optional at form level;
        # model.clean() enforces them only when is_seasonal=True
        for f in ['season_start_month', 'season_start_day',
                  'season_end_month',   'season_end_day']:
            self.fields[f].required = False