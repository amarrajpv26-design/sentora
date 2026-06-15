from django import forms

from .models import Coupon


class CouponForm(forms.ModelForm):
    valid_from = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
        ),
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    valid_to = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
        ),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    class Meta:
        model = Coupon
        fields = [
            "code",
            "description",
            "is_fixed",
            "discount",
            "max_discount_amount",
            "min_purchase",
            "valid_from",
            "valid_to",
            "usage_limit",
            "usage_limit_per_user",
            "active",
        ]
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "e.g. WELCOME20"}),
            "description": forms.TextInput(
                attrs={"placeholder": "Shown to customers, e.g. 'Welcome offer'"}
            ),
            "discount": forms.NumberInput(attrs={"min": 1}),
            "max_discount_amount": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
            "min_purchase": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
            "usage_limit": forms.NumberInput(attrs={"min": 0}),
            "usage_limit_per_user": forms.NumberInput(attrs={"min": 0}),
        }

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        if not code:
            raise forms.ValidationError("Coupon code cannot be empty.")

        qs = Coupon.objects.filter(code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise forms.ValidationError("A coupon with this code already exists.")

        return code

    def clean(self):
        cleaned_data = super().clean()

        is_fixed = cleaned_data.get("is_fixed")
        discount = cleaned_data.get("discount")
        max_discount_amount = cleaned_data.get("max_discount_amount")
        min_purchase = cleaned_data.get("min_purchase")
        valid_from = cleaned_data.get("valid_from")
        valid_to = cleaned_data.get("valid_to")

        if discount is not None:
            if discount <= 0:
                self.add_error("discount", "Discount must be greater than zero.")
            elif not is_fixed and discount > 100:
                self.add_error("discount", "Percentage discount cannot exceed 100.")

        if not is_fixed:
            if not max_discount_amount:
                self.add_error(
                    "max_discount_amount",
                    "A maximum discount cap is required for percentage coupons.",
                )
            elif max_discount_amount <= 0:
                self.add_error(
                    "max_discount_amount", "Maximum discount must be greater than zero."
                )
        elif max_discount_amount is not None and max_discount_amount <= 0:
            self.add_error(
                "max_discount_amount", "Maximum discount must be greater than zero."
            )

        if min_purchase is not None and min_purchase < 0:
            self.add_error("min_purchase", "Minimum purchase cannot be negative.")

        if valid_from and valid_to and valid_from >= valid_to:
            self.add_error("valid_to", "End date must be after the start date.")

        return cleaned_data