from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from .models import ProductOffer, CategoryOffer, ReferralOffer, ReferralUsage
from .forms import ProductOfferForm, CategoryOfferForm, ReferralOfferForm
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from .utils import get_qualifying_orders, REFERRAL_AUTO_UNLOCK_THRESHOLD

# ──────────────────────────────────────────────
#  PRODUCT OFFERS
# ──────────────────────────────────────────────


@staff_member_required(login_url="admin_login")
def offer_dashboard(request):
    now = timezone.now()

    product_list = ProductOffer.objects.select_related("product").order_by(
        "-created_at"
    )
    product_paginator = Paginator(product_list, 5)
    product_offers = product_paginator.get_page(request.GET.get("product_page"))

    category_list = CategoryOffer.objects.select_related("category").order_by(
        "-created_at"
    )
    category_paginator = Paginator(category_list, 5)
    category_offers = category_paginator.get_page(request.GET.get("category_page"))

    brand_list = BrandOffer.objects.select_related("brand").order_by(
        "-created_at"
    )  # ← NEW
    brand_paginator = Paginator(brand_list, 5)
    brand_offers = brand_paginator.get_page(request.GET.get("brand_page"))

    referral_list = ReferralOffer.objects.select_related("referrer").order_by(
        "-created_at"
    )
    referral_paginator = Paginator(referral_list, 5)
    referral_offers = referral_paginator.get_page(request.GET.get("referral_page"))

    context = {
        "product_offers": product_offers,
        "category_offers": category_offers,
        "brand_offers": brand_offers,  # ← NEW
        "referral_offers": referral_offers,
        "now": now,
    }
    return render(request, "offers/dashboard.html", context)


@staff_member_required(login_url="admin_login")
def product_offer_create(request):
    form = ProductOfferForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Product offer created successfully.")
        return redirect("offers:dashboard")
    return render(
        request,
        "offers/product_offer_form.html",
        {"form": form, "title": "New Product Offer"},
    )


@staff_member_required(login_url="admin_login")
def product_offer_edit(request, pk):
    offer = get_object_or_404(ProductOffer, pk=pk)
    form = ProductOfferForm(request.POST or None, instance=offer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Product offer updated.")
        return redirect("offers:dashboard")
    return render(
        request,
        "offers/product_offer_form.html",
        {"form": form, "title": "Edit Product Offer", "offer": offer},
    )


@staff_member_required(login_url="admin_login")
def product_offer_toggle(request, pk):
    offer = get_object_or_404(ProductOffer, pk=pk)
    offer.is_active = not offer.is_active
    offer.save()
    state = "activated" if offer.is_active else "deactivated"
    messages.success(request, f"Offer '{offer.name}' {state}.")
    return redirect("offers:dashboard")


@staff_member_required(login_url="admin_login")
def product_offer_delete(request, pk):
    offer = get_object_or_404(ProductOffer, pk=pk)
    if request.method == "POST":
        offer.delete()
        messages.success(request, "Product offer deleted.")
        return redirect("offers:dashboard")
    return render(
        request,
        "offers/confirm_delete.html",
        {"offer": offer, "offer_type": "Product Offer"},
    )


# ──────────────────────────────────────────────
#  CATEGORY OFFERS
# ──────────────────────────────────────────────


@staff_member_required(login_url="admin_login")
def category_offer_create(request):
    form = CategoryOfferForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category offer created successfully.")
        return redirect("offers:dashboard")
    return render(
        request,
        "offers/category_offer_form.html",
        {"form": form, "title": "New Category Offer"},
    )


@staff_member_required(login_url="admin_login")
def category_offer_edit(request, pk):
    offer = get_object_or_404(CategoryOffer, pk=pk)
    form = CategoryOfferForm(request.POST or None, instance=offer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Category offer updated.")
        return redirect("offers:dashboard")
    return render(
        request,
        "offers/category_offer_form.html",
        {"form": form, "title": "Edit Category Offer", "offer": offer},
    )


@staff_member_required(login_url="admin_login")
def category_offer_toggle(request, pk):
    offer = get_object_or_404(CategoryOffer, pk=pk)
    offer.is_active = not offer.is_active
    offer.save()
    state = "activated" if offer.is_active else "deactivated"
    messages.success(request, f"Offer '{offer.name}' {state}.")
    return redirect("offers:dashboard")


@staff_member_required(login_url="admin_login")
def category_offer_delete(request, pk):
    offer = get_object_or_404(CategoryOffer, pk=pk)
    if request.method == "POST":
        offer.delete()
        messages.success(request, "Category offer deleted.")
        return redirect("offers:dashboard")
    return render(
        request,
        "offers/confirm_delete.html",
        {"offer": offer, "offer_type": "Category Offer"},
    )


# ──────────────────────────────────────────────
#  REFERRAL OFFERS
# ──────────────────────────────────────────────


@staff_member_required(login_url="admin_login")
def referral_offer_create(request):
    form = ReferralOfferForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Referral offer created.")
        return redirect("offers:dashboard")
    return render(
        request,
        "offers/referral_offer_form.html",
        {"form": form, "title": "New Referral Offer"},
    )


@staff_member_required(login_url="admin_login")
def referral_offer_edit(request, pk):
    offer = get_object_or_404(ReferralOffer, pk=pk)
    form = ReferralOfferForm(request.POST or None, instance=offer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Referral offer updated.")
        return redirect("offers:dashboard")
    return render(
        request,
        "offers/referral_offer_form.html",
        {"form": form, "title": "Edit Referral Offer", "offer": offer},
    )


@staff_member_required(login_url="admin_login")
def referral_offer_toggle(request, pk):
    offer = get_object_or_404(ReferralOffer, pk=pk)
    offer.is_active = not offer.is_active
    offer.save()
    state = "activated" if offer.is_active else "deactivated"
    messages.success(
        request, f"Referral offer for '{offer.referrer.username}' {state}."
    )
    return redirect("offers:dashboard")


@staff_member_required(login_url="admin_login")
def referral_offer_delete(request, pk):
    offer = get_object_or_404(ReferralOffer, pk=pk)
    if request.method == "POST":
        offer.delete()
        messages.success(request, "Referral offer deleted.")
        return redirect("offers:dashboard")
    return render(
        request,
        "offers/confirm_delete.html",
        {"offer": offer, "offer_type": "Referral Offer"},
    )


@staff_member_required(login_url="admin_login")
def referral_offer_detail(request, pk):
    """Shows usage stats and token URL for a referral offer."""
    offer = get_object_or_404(ReferralOffer, pk=pk)
    usages = (
        ReferralUsage.objects.filter(referral_offer=offer)
        .select_related("referee")
        .order_by("-created_at")
    )
    return render(
        request, "offers/referral_detail.html", {"offer": offer, "usages": usages}
    )


# ──────────────────────────────────────────────
#  PUBLIC: Referral token signup handler
# ──────────────────────────────────────────────


def referral_signup_redirect(request, token):
    """
    Stores the referral token in the session so it can be
    processed after the user completes signup.
    Then redirects to the signup page.
    """
    offer = get_object_or_404(ReferralOffer, token=token, is_active=True)
    request.session["referral_token"] = str(offer.token)
    messages.info(
        request,
        f"You've been referred by {offer.referrer.username}! Sign up to claim your bonus.",
    )
    return redirect("user_signup")


@login_required
def my_referral_view(request):
    from .utils import maybe_auto_unlock_referral

    maybe_auto_unlock_referral(request.user)
    referral_offer = ReferralOffer.objects.filter(referrer=request.user).first()

    progress = None
    usages = []

    if referral_offer:
        usages = referral_offer.usages.select_related("referee").order_by("-created_at")
    else:
        spent = (
            get_qualifying_orders(request.user).aggregate(total=Sum("total_amount"))[
                "total"
            ]
            or 0
        )
        progress = {
            "spent": spent,
            "threshold": REFERRAL_AUTO_UNLOCK_THRESHOLD,
            "remaining": max(REFERRAL_AUTO_UNLOCK_THRESHOLD - spent, 0),
            "percent": min(int((spent / REFERRAL_AUTO_UNLOCK_THRESHOLD) * 100), 100),
        }

    return render(
        request,
        "offers/my_referrals.html",
        {"referral_offer": referral_offer, "progress": progress, "usages": usages},
    )


from .models import ProductOffer, CategoryOffer, ReferralOffer, BrandOffer
from .forms import (
    ProductOfferForm,
    CategoryOfferForm,
    ReferralOfferForm,
    BrandOfferForm,
)

# ──────────────────────────────────────────────
#  BRAND OFFERS
# ──────────────────────────────────────────────


@staff_member_required(login_url="admin_login")
def brand_offer_create(request):
    form = BrandOfferForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Brand offer created successfully.")
        return redirect("offers:dashboard")
    return render(
        request,
        "offers/brand_offer_form.html",
        {"form": form, "title": "New Brand Offer"},
    )


@staff_member_required(login_url="admin_login")
def brand_offer_edit(request, pk):
    offer = get_object_or_404(BrandOffer, pk=pk)
    form = BrandOfferForm(request.POST or None, instance=offer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Brand offer updated.")
        return redirect("offers:dashboard")
    return render(
        request,
        "offers/brand_offer_form.html",
        {"form": form, "title": "Edit Brand Offer", "offer": offer},
    )


@staff_member_required(login_url="admin_login")
def brand_offer_toggle(request, pk):
    offer = get_object_or_404(BrandOffer, pk=pk)
    offer.is_active = not offer.is_active
    offer.save()
    state = "activated" if offer.is_active else "deactivated"
    messages.success(request, f"Offer '{offer.name}' {state}.")
    return redirect("offers:dashboard")


@staff_member_required(login_url="admin_login")
def brand_offer_delete(request, pk):
    offer = get_object_or_404(BrandOffer, pk=pk)
    if request.method == "POST":
        offer.delete()
        messages.success(request, "Brand offer deleted.")
        return redirect("offers:dashboard")
    return render(
        request,
        "offers/confirm_delete.html",
        {"offer": offer, "offer_type": "Brand Offer"},
    )
