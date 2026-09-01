import re
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.core.files.uploadedfile import UploadedFile

from django import forms
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth import get_user_model
from .models import User, Address
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.contrib.auth.forms import SetPasswordForm

User = get_user_model()


# Server-side username rule (mirrors the JS check in signup.html):
# 3-20 chars, must start with a letter, only letters/numbers/underscore after that.
USERNAME_REGEX = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{2,19}$")


from PIL import Image, UnidentifiedImageError


def validate_profile_image(image_file):
    """Returns an error message string if invalid, or None if valid."""

    # 5 MB limit
    if image_file.size > 5 * 1024 * 1024:
        return "Image must be smaller than 5MB."

    # Check extension
    valid_extensions = {".jpg", ".jpeg", ".png", ".webp"}

    filename = image_file.name.lower()
    ext = "." + filename.rsplit(".", 1)[1] if "." in filename else ""

    if ext not in valid_extensions:
        return "Only JPG, JPEG, PNG, and WEBP images are allowed."

    # Validate actual image
    try:
        image_file.seek(0)

        img = Image.open(image_file)
        img.verify()

        # Reset file pointer after verification
        image_file.seek(0)

    except (UnidentifiedImageError, OSError, ValueError):
        return "The uploaded file is not a valid image."

    return None


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
    phone_validator = RegexValidator(
        r"^[6-9]\d{9}$",
        "Enter a valid 10-digit Indian mobile number (must start with 6-9).",
    )
    phone_number = forms.CharField(validators=[phone_validator], required=False)

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

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if not USERNAME_REGEX.match(username):
            raise forms.ValidationError(
                "Username must be 3-20 characters, start with a letter, and contain "
                "only letters, numbers, and underscores."
            )
        existing = User.objects.filter(username=username)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError(
                f"The identity '{username}' is already claimed."
            )
        return username

    def clean_first_name(self):
        name = self.cleaned_data.get("first_name", "").strip()
        if name and not re.match(r"^[A-Za-z\s]+$", name):
            raise forms.ValidationError("First name can only contain letters.")
        return name

    def clean_last_name(self):
        name = self.cleaned_data.get("last_name", "").strip()
        if name and not re.match(r"^[A-Za-z\s]+$", name):
            raise forms.ValidationError("Last name can only contain letters.")
        return name

    def clean_profile_image(self):
        image = self.cleaned_data.get("profile_image")
        if image and hasattr(image, "size"):
            error = validate_profile_image(image)
            if error:
                raise forms.ValidationError(error)
        return image


class AddressForm(forms.ModelForm):
    # Strict validators for a luxury app
    phone_validator = RegexValidator(
        r"^[6-9]\d{9}$",
        "Enter a valid 10-digit Indian mobile number (must start with 6-9).",
    )
    pincode_validator = RegexValidator(
        r"^[1-9]\d{5}$", "Enter a valid 6-digit postal code (cannot start with 0)."
    )

    full_name = forms.CharField(min_length=3, max_length=100)
    phone_number = forms.CharField(validators=[phone_validator])
    pincode = forms.CharField(validators=[pincode_validator])

    # Explicitly declared (rather than left to the ModelForm machinery) so
    # that it is unambiguously a plain optional checkbox: unchecked must mean
    # False, not "missing/invalid". This is what actually fixes the
    # "Please correct the marked fields below" error on an unchecked box.
    is_default = forms.BooleanField(required=False)

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
            "is_default",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Ensure every real address field is required, EXCEPT:
        #  - address_line_2 (genuinely optional, e.g. no apartment/suite)
        #  - is_default (a checkbox; unchecked must be allowed to mean False,
        #    never treated as a validation error)
        NOT_REQUIRED = ("address_line_2", "is_default")

        for field_name, field in self.fields.items():
            if field_name not in NOT_REQUIRED:
                field.required = True

            # Apply your luxury styling
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update(
                    {
                        "class": "w-full bg-transparent border-b border-neutral-border py-3 outline-none focus:border-primary transition-colors text-sm text-white",
                        "placeholder": f"Enter {field_name.replace('_', ' ').title()}",
                    }
                )

        # Belt-and-suspenders: guarantee is_default is optional even if the
        # loop above or Meta ever changes, since this is the field that was
        # silently breaking first-time address submission.
        self.fields["is_default"].required = False

        # Client-side hints so the browser catches obvious mistakes immediately.
        # These are just UX hints — the clean_* methods below are the real, authoritative check.
        self.fields["full_name"].widget.attrs.update(
            {
                "pattern": "[A-Za-z ]+",
                "title": "Only letters and spaces are allowed.",
            }
        )
        self.fields["city"].widget.attrs.update(
            {
                "pattern": "[A-Za-z ]+",
                "title": "Only letters and spaces are allowed.",
            }
        )
        self.fields["state"].widget.attrs.update(
            {
                "pattern": "[A-Za-z ]+",
                "title": "Only letters and spaces are allowed.",
            }
        )
        self.fields["phone_number"].widget.attrs.update(
            {
                "pattern": "[6-9][0-9]{9}",
                "inputmode": "numeric",
                "maxlength": "10",
                "title": "10-digit mobile number starting with 6-9.",
            }
        )
        self.fields["pincode"].widget.attrs.update(
            {
                "pattern": "[1-9][0-9]{5}",
                "inputmode": "numeric",
                "maxlength": "6",
                "title": "6-digit pincode, cannot start with 0.",
            }
        )

    # --- Server-side validation (authoritative — always runs regardless of browser support) ---

    def clean_full_name(self):
        name = self.cleaned_data.get("full_name", "").strip()
        if not re.match(r"^[A-Za-z\s]+$", name):
            raise ValidationError("Full name can only contain letters and spaces.")
        return name.title()  # Auto-capitalizes "amar raj" to "Amar Raj"

    def clean_city(self):
        city = self.cleaned_data.get("city", "").strip()
        if not re.match(r"^[A-Za-z\s]+$", city):
            raise ValidationError("City can only contain letters and spaces.")
        return city.capitalize()

    def clean_state(self):
        state = self.cleaned_data.get("state", "").strip()
        if not re.match(r"^[A-Za-z\s]+$", state):
            raise ValidationError("State can only contain letters and spaces.")
        return state.capitalize()

    def clean_address_line_1(self):
        address = self.cleaned_data.get("address_line_1", "").strip()
        if len(address) < 5:
            raise ValidationError("Address must be at least 5 characters long.")
        return address


class YourPasswordChangeForm(forms.Form):  # Or use PasswordChangeForm
    # ... your fields ...

    def clean_new_password(self):
        password = self.cleaned_data.get("new_password")

        if len(password) < 8:
            raise ValidationError("Security requirement: Minimum 8 characters.")

        if not re.search(r"[A-Z]", password):
            raise ValidationError(
                "Security requirement: At least one uppercase letter."
            )

        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            raise ValidationError(
                "Security requirement: At least one special character."
            )

        return password


from django.contrib.auth.forms import SetPasswordForm


class ScentoraSetPasswordForm(SetPasswordForm):
    def clean_new_password1(self):
        password = self.cleaned_data.get("new_password1")
        if password and self.user.check_password(password):
            raise ValidationError(
                "Security requirement: New password cannot be the same as your current password."
            )
        return password


from django.core.validators import RegexValidator


class UserProfileForm(forms.ModelForm):
    phone_validator = RegexValidator(
        r"^[6-9]\d{9}$",
        "Enter a valid 10-digit Indian mobile number (must start with 6-9).",
    )
    phone_number = forms.CharField(validators=[phone_validator], required=False)

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

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if not USERNAME_REGEX.match(username):
            raise forms.ValidationError(
                "Username must be 3-20 characters, start with a letter, and contain "
                "only letters, numbers, and underscores."
            )
        existing = User.objects.filter(username=username)
        if self.instance.pk:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise forms.ValidationError(
                f"The identity '{username}' is already claimed."
            )
        return username

    def clean_first_name(self):
        name = self.cleaned_data.get("first_name", "").strip()
        if name and not re.match(r"^[A-Za-z\s]+$", name):
            raise forms.ValidationError("First name can only contain letters.")
        return name

    def clean_last_name(self):
        name = self.cleaned_data.get("last_name", "").strip()
        if name and not re.match(r"^[A-Za-z\s]+$", name):
            raise forms.ValidationError("Last name can only contain letters.")
        return name

    def clean_profile_image(self):
        image = self.cleaned_data.get("profile_image")
        # Only validate genuinely NEW uploads — request.FILES holds newly
        # submitted files. An unchanged existing image comes through
        # cleaned_data too (ModelForm keeps it when no new file is chosen),
        # but it's never in request.FILES, so skip validation for it.
        if image and isinstance(image, UploadedFile):
            error = validate_profile_image(image)
            if error:
                raise forms.ValidationError(error)
        return image