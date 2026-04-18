from django import forms
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth import get_user_model
from .models import User, Address
from django.core.validators import RegexValidator
import re
from django.core.exceptions import ValidationError

User = get_user_model()


class ScentoraPasswordResetForm(PasswordResetForm):
    def get_users(self, email):
        """
        Overrides the default check to include users who may have
        signed up via Google OAuth and don't have a password yet.
        """
        return User.objects.filter(email__iexact=email, is_active=True)

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if not User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "This identity is not registered in the Scentora vault."
            )
        return email  # Fixed the typo here


class UserEditForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Adding those luxury Tailwind classes to every field automatically
        for field in self.fields.values():
            field.widget.attrs.update(
                {
                    "class": "w-full bg-transparent border-b border-neutral-border py-3 outline-none focus:border-primary transition-colors text-sm"
                }
            )

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "username",
            "phone_number",
            "profile_image",
        ]


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "username",
            "phone_number",
            "profile_image",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update(
                {
                    "class": "w-full bg-transparent border-b border-neutral-border py-3 outline-none focus:border-primary transition-colors text-sm"
                }
            )


class AddressForm(forms.ModelForm):
    # Strict validators for a luxury app
    phone_validator = RegexValidator(r'^\d{10}$', 'Enter a valid 10-digit mobile number.')
    pincode_validator = RegexValidator(r'^\d{6}$', 'Enter a valid 6-digit postal code.')

    full_name = forms.CharField(min_length=3, max_length=100)
    phone_number = forms.CharField(validators=[phone_validator])
    pincode = forms.CharField(validators=[pincode_validator])

    class Meta:
        model = Address
        fields = [
            "full_name",
            "phone_number",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "pincode",
            "address_type",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure every field is required (except address_line_2)
        for field_name, field in self.fields.items():
            if field_name != 'address_line_2':
                field.required = True
            
            # Apply your luxury styling
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({
                    "class": "w-full bg-transparent border-b border-neutral-border py-3 outline-none focus:border-primary transition-colors text-sm text-white",
                    "placeholder": f"Enter {field_name.replace('_', ' ').title()}"
                })

    # Custom cleaning to ensure data is polished
    def clean_full_name(self):
        name = self.cleaned_data.get('full_name')
        return name.strip().title() # Auto-capitalizes "amar raj" to "Amar Raj"

    def clean_city(self):
        return self.cleaned_data.get('city').strip().capitalize()


class YourPasswordChangeForm(forms.Form): # Or use PasswordChangeForm
    # ... your fields ...

    def clean_new_password(self):
        password = self.cleaned_data.get('new_password')
        
        if len(password) < 8:
            raise ValidationError("Security requirement: Minimum 8 characters.")
            
        if not re.search(r'[A-Z]', password):
            raise ValidationError("Security requirement: At least one uppercase letter.")
            
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise ValidationError("Security requirement: At least one special character.")
            
        return password