from django import forms
from .models import ProductOffer, CategoryOffer, ReferralOffer


class ProductOfferForm(forms.ModelForm):
    class Meta:
        model = ProductOffer
        fields = [
            "name",
            "description",
            "product",
            "discount_type",
            "discount_value",
            "start_date",
            "end_date",
            "is_active",
        ]
        widgets = {
            "start_date": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "end_date": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-format datetime values for the input widget
        if self.instance and self.instance.pk:
            if self.instance.start_date:
                self.initial["start_date"] = self.instance.start_date.strftime(
                    "%Y-%m-%dT%H:%M"
                )
            if self.instance.end_date:
                self.initial["end_date"] = self.instance.end_date.strftime(
                    "%Y-%m-%dT%H:%M"
                )


class CategoryOfferForm(forms.ModelForm):
    class Meta:
        model = CategoryOffer
        fields = [
            "name",
            "description",
            "category",
            "discount_type",
            "discount_value",
            "start_date",
            "end_date",
            "is_active",
        ]
        widgets = {
            "start_date": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "end_date": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.start_date:
                self.initial["start_date"] = self.instance.start_date.strftime(
                    "%Y-%m-%dT%H:%M"
                )
            if self.instance.end_date:
                self.initial["end_date"] = self.instance.end_date.strftime(
                    "%Y-%m-%dT%H:%M"
                )


class ReferralOfferForm(forms.ModelForm):
    class Meta:
        model = ReferralOffer
        fields = [
            "referrer",
            "referral_code",
            "referrer_reward_type",
            "referrer_reward_value",
            "referee_reward_type",
            "referee_reward_value",
            "max_uses",
            "is_active",
        ]