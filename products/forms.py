from django import forms
from .models import Category

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description', 'category_image', 'is_active', 'show_in_nav', 'is_featured']
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
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Force these fields to be required in the Django logic
        self.fields['name'].required = True
        self.fields['description'].required = True
        # Note: BooleanFields (toggles) are handled as True/False, 
        # so they technically always have a value.