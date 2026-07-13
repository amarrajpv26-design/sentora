# coupons/views.py
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from django.contrib import messages
from .models import Coupon
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import CouponForm
from .models import Coupon


@require_POST
def apply_coupon(request):
    code = request.POST.get("code")
    # Get total from your existing cart logic
    # We'll calculate total here to validate min_purchase
    subtotal = float(request.POST.get("subtotal", 0))

    try:
        coupon = Coupon.objects.get(code__iexact=code, active=True)
        is_valid, message = coupon.is_valid(subtotal)

        if is_valid:
            request.session["coupon_id"] = coupon.id
            messages.success(request, f"Coupon '{code}' applied successfully!")
        else:
            messages.error(request, message)

    except Coupon.DoesNotExist:
        messages.error(request, "Invalid coupon code.")

    return redirect("checkout")


def remove_coupon(request):
    if "coupon_id" in request.session:
        del request.session["coupon_id"]
        messages.success(request, "Coupon removed.")
    return redirect("checkout")


@staff_member_required
def admin_coupon_list(request):
    coupons = Coupon.objects.all()

    search_query = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "")
    sort = request.GET.get("sort", "newest")

    if search_query:
        coupons = coupons.filter(
            Q(code__icontains=search_query) | Q(description__icontains=search_query)
        )

    now = timezone.now()

    if status_filter == "active":
        coupons = coupons.filter(
            active=True, valid_from__lte=now, valid_to__gte=now
        ).filter(Q(usage_limit=0) | Q(used_count__lt=F("usage_limit")))
    elif status_filter == "scheduled":
        coupons = coupons.filter(active=True, valid_from__gt=now)
    elif status_filter == "expired":
        coupons = coupons.filter(active=True, valid_to__lt=now)
    elif status_filter == "exhausted":
        coupons = coupons.filter(
            active=True, usage_limit__gt=0, used_count__gte=F("usage_limit")
        )
    elif status_filter == "inactive":
        coupons = coupons.filter(active=False)

    sort_map = {
        "newest": "-created_at",
        "oldest": "created_at",
        "expiring_soon": "valid_to",
        "code": "code",
    }
    coupons = coupons.order_by(sort_map.get(sort, "-created_at"))

    paginator = Paginator(coupons, 2)
    coupons_page = paginator.get_page(request.GET.get("page"))

    context = {
        "coupons": coupons_page,
        "search_query": search_query,
        "status_filter": status_filter,
        "sort": sort,
    }
    return render(request, "coupons/coupon_list.html", context)


@staff_member_required
def admin_coupon_create(request):
    if request.method == "POST":
        form = CouponForm(request.POST)
        if form.is_valid():
            coupon = form.save()
            messages.success(request, f"Coupon '{coupon.code}' created successfully.")
            return redirect("coupons:admin_coupon_list")
        messages.error(request, "Please fix the errors below.")
    else:
        form = CouponForm()

    return render(
        request,
        "coupons/coupon_form.html",
        {"form": form, "is_edit": False},
    )


@staff_member_required
def admin_coupon_edit(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)

    if request.method == "POST":
        form = CouponForm(request.POST, instance=coupon)
        if form.is_valid():
            form.save()
            messages.success(request, f"Coupon '{coupon.code}' updated successfully.")
            return redirect("coupons:admin_coupon_list")
        messages.error(request, "Please fix the errors below.")
    else:
        form = CouponForm(instance=coupon)

    return render(
        request,
        "coupons/coupon_form.html",
        {"form": form, "is_edit": True, "coupon": coupon},
    )


@staff_member_required
def admin_coupon_delete(request, pk):
    coupon = get_object_or_404(Coupon, pk=pk)

    if request.method == "POST":
        if coupon.is_used:
            coupon.active = False
            coupon.save(update_fields=["active"])
            messages.success(
                request,
                f"'{coupon.code}' has order history, so it was deactivated "
                f"instead of deleted and is now hidden from customers.",
            )
        else:
            code = coupon.code
            coupon.delete()
            messages.success(request, f"Coupon '{code}' deleted successfully.")

    return redirect("coupons:admin_coupon_list")
