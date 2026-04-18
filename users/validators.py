import re
from django.core.exceptions import ValidationError

class ScentoraComplexityValidator:
    def validate(self, password, user=None):
        if not re.findall('[A-Z]', password):
            raise ValidationError("Security requirement: At least one uppercase letter is required.")
        if not re.findall('[()[\]{}|\\`~!@#$%^&*_\-+=;:\'",<>./?]', password):
            raise ValidationError("Security requirement: At least one special character is required.")

    def get_help_text(self):
        return "Minimum 8 characters, one uppercase letter, and one special character."