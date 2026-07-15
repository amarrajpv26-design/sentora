import re
from django.core.exceptions import ValidationError


class ScentoraComplexityValidator:
    def validate(self, password, user=None):
        if len(password) < 8:
            raise ValidationError(
                "Security requirement: Password must be at least 8 characters."
            )
        if not re.findall("[A-Z]", password):
            raise ValidationError(
                "Security requirement: At least one uppercase letter is required."
            )
        if not re.findall("[0-9]", password):
            raise ValidationError(
                "Security requirement: At least one number is required."
            )
        if not re.findall("[()[\]{}|\\`~!@#$%^&*_\-+=;:'\",<>./?]", password):
            raise ValidationError(
                "Security requirement: At least one special character is required."
            )

    def get_help_text(self):
        return "Minimum 8 characters, one uppercase letter, one number, and one special character."
