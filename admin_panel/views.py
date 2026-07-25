from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.cache import never_cache
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.auth.decorators import user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth
from orders.models import Order, OrderItem
from products.models import Product, ProductVariant, Category, Brand
from coupons.models import CouponUsage
from offers.models import ReferralUsage
from wallets.models import Wallet, WalletTransaction
from users.models import User
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta

from users.models import User
from products.models import Product, Category, Brand, ProductVariant
from orders.models import Order, OrderItem
from coupons.models import Coupon
from offers.models import ReferralUsage
import json
from django.db.models.functions import (
    TruncDate,
    TruncMonth,
    TruncYear,
)

User = get_user_model()


def is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@never_cache
@user_passes_test(is_admin, login_url="admin_login")
def admin_dashboard(request):

    filter_type = request.GET.get("filter", "daily")

    # =========================
    # TOP CARDS
    # =========================

    total_users = User.objects.filter(is_superuser=False).count()

    total_orders = Order.objects.count()

    total_revenue = (
        Order.objects.filter(payment_status="PAID").aggregate(
            total=Sum("total_amount")
        )["total"]
        or 0
    )

    total_products = Product.objects.count()

    # =========================
    # RECENT ORDERS
    # =========================

    recent_orders = Order.objects.select_related("user").order_by("-created_at")[:10]

    # =========================
    # RECENT USERS
    # =========================

    latest_users = User.objects.filter(is_superuser=False).order_by("-date_joined")[:5]

    # =========================
    # ORDER STATUS COUNTS
    # =========================

    pending_orders = Order.objects.filter(order_status="PENDING").count()

    delivered_orders = Order.objects.filter(order_status="DELIVERED").count()

    cancelled_orders = Order.objects.filter(order_status="CANCELLED").count()

    # =========================
    # LOW STOCK
    # =========================

    low_stock_products = (
        ProductVariant.objects.filter(stock__lt=10)
        .select_related("product")
        .order_by("stock")[:5]
    )

    best_selling_products = (
        OrderItem.objects.values(
            "product_variant__product__id", "product_variant__product__name"
        )
        .annotate(total_sold=Sum("quantity"))
        .order_by("-total_sold")[:5]
    )

    best_selling_categories = (
        OrderItem.objects.values(
            "product_variant__product__categories__id",
            "product_variant__product__categories__name",
        )
        .annotate(total_sold=Sum("quantity"))
        .order_by("-total_sold")[:5]
    )

    best_selling_brands = (
        OrderItem.objects.values(
            "product_variant__product__brand__id",
            "product_variant__product__brand__name",
        )
        .annotate(total_sold=Sum("quantity"))
        .order_by("-total_sold")[:5]
    )

    # =========================
    # COUPONS
    # =========================

    active_coupons = Coupon.objects.filter(active=True).count()

    # =========================
    # REFERRALS
    # =========================

    total_referrals = ReferralUsage.objects.count()

    sales_data = None

    if filter_type == "monthly":
        sales_data = (
            Order.objects.filter(payment_status="PAID")
            .annotate(period=TruncMonth("created_at"))
            .values("period")
            .annotate(total=Sum("total_amount"))
            .order_by("period")
        )
    elif filter_type == "yearly":
        sales_data = (
            Order.objects.filter(payment_status="PAID")
            .annotate(period=TruncYear("created_at"))
            .values("period")
            .annotate(total=Sum("total_amount"))
            .order_by("period")
        )
    else:
        sales_data = (
            Order.objects.filter(payment_status="PAID")
            .annotate(period=TruncDate("created_at"))
            .values("period")
            .annotate(total=Sum("total_amount"))
            .order_by("period")
        )

    chart_labels = []
    chart_data = []

    for item in sales_data:
        if filter_type == "yearly":
            label = item["period"].strftime("%Y")
        elif filter_type == "monthly":
            label = item["period"].strftime("%b %Y")
        else:
            label = item["period"].strftime("%d %b")

        chart_labels.append(label)
        chart_data.append(float(item["total"]))

    activities = []

    for order in Order.objects.select_related("user").order_by("-created_at")[:5]:
        activities.append(
            {
                "icon": "bag",
                "color": "gold",
                "title": f"Order #{order.order_id}",
                "subtitle": f"{order.user.username} placed a new order",
                "time": order.created_at,
            }
        )

    # Delivered Orders
    for order in Order.objects.filter(order_status="DELIVERED").order_by("-updated_at")[
        :3
    ]:
        activities.append(
            {
                "icon": "truck",
                "color": "green",
                "title": "Order Delivered",
                "subtitle": f"Order #{order.order_id} delivered successfully",
                "time": order.updated_at,
            }
        )

    # Cancelled Orders
    for order in Order.objects.filter(order_status="CANCELLED").order_by("-updated_at")[
        :3
    ]:
        activities.append(
            {
                "icon": "x-circle",
                "color": "red",
                "title": "Order Cancelled",
                "subtitle": f"Order #{order.order_id} cancelled",
                "time": order.updated_at,
            }
        )
    # Return Requests
    for order in Order.objects.filter(order_status="RETURN_REQUESTED").order_by(
        "-updated_at"
    )[:3]:
        activities.append(
            {
                "icon": "arrow-counterclockwise",
                "color": "orange",
                "title": "Return Requested",
                "subtitle": f"Order #{order.order_id} requested for return",
                "time": order.updated_at,
            }
        )

    activities = sorted(activities, key=lambda x: x["time"], reverse=True)[:15]

    context = {
        "total_users": total_users,
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "total_products": total_products,
        "recent_orders": recent_orders,
        "latest_users": latest_users,
        "pending_orders": pending_orders,
        "delivered_orders": delivered_orders,
        "cancelled_orders": cancelled_orders,
        "low_stock_products": low_stock_products,
        "best_selling_products": best_selling_products,
        "best_selling_categories": best_selling_categories,
        "best_selling_brands": best_selling_brands,
        "active_coupons": active_coupons,
        "filter_type": filter_type,
        "total_referrals": total_referrals,
        "chart_labels": json.dumps(chart_labels),
        "chart_data": json.dumps(chart_data),
        "activities": activities,
    }

    return render(
        request,
        "admin_panel/dashboard.html",
        context,
    )


@never_cache
def admin_login(request):

    if request.user.is_authenticated and request.user.is_staff:
        return redirect("admin_dashboard")

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, email=email, password=password)

        if user is not None and user.is_staff:
            login(request, user)

            return redirect("admin_dashboard")
        else:
            messages.error(request, "Invalid credentials or not authorized.")
    return render(request, "admin_panel/login.html")


@never_cache
def admin_logout(request):
    if request.method == "POST":
        logout(request)
        messages.success(request, "You have been logged out successfully.")
        return redirect("admin_login")

    return render(request, "admin_panel/confirm_logout.html")


@never_cache
@staff_member_required(login_url="admin_login")
def user_management(request):
    users = User.objects.filter(is_superuser=False).order_by("-date_joined")

    search_query = request.GET.get("search", "")
    if search_query:
        users = users.filter(
            Q(username__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
        )

    status_filter = request.GET.get("status", "")
    if status_filter == "active":
        users = users.filter(is_active=True)
    elif status_filter == "blocked":
        users = users.filter(is_active=False)

    sort_order = request.GET.get("sort", "newest")
    if sort_order == "oldest":
        users = users.order_by("date_joined")
    elif sort_order == "alpha":
        users = users.order_by("username")
    elif sort_order == "dob":
        users = users.order_by("dob")
    else:
        users = users.order_by("-date_joined")

    active_count = users.filter(is_active=True, is_superuser=False).count()
    blocked_count = users.filter(is_active=False, is_superuser=False).count()
    total_count = users.count()

    paginator = Paginator(users, 5)
    page_number = request.GET.get("page")
    users = paginator.get_page(page_number)

    context = {
        "users": users,
        "active_count": active_count,
        "blocked_count": blocked_count,
        "total_count": total_count,
        "search_query": search_query,
        "status_filter": status_filter,
        "sort_order": sort_order,
    }

    return render(request, "admin_panel/user_management.html", context)


@never_cache
@staff_member_required(login_url="admin_login")
def user_detail_view(request, user_id):
    customer = get_object_or_404(User, id=user_id)

    orders = []

    context = {
        "customer": customer,
        "orders": orders,
        "total_spent": "0.00",
    }
    return render(request, "admin_panel/user_detail.html", context)


@never_cache
@staff_member_required(login_url="admin_login")
def toggle_user_status(request, user_id):
    if request.method == "POST":
        user = get_object_or_404(User, id=user_id)

        if user.is_active:
            user.is_active = False
            action = "blocked"
        else:
            user.is_active = True
            action = "unblocked"

        user.save()
        messages.success(
            request, f"User {user.username} has been successfully {action}."
        )
        return redirect("user_management")

    return redirect("user_management")


@never_cache
def confirm_block_user(request, user_id):
    user_to_manage = get_object_or_404(User, id=user_id)

    if request.method == "POST":
        # Toggle the active status
        if user_to_manage.is_active:
            user_to_manage.is_active = False
            action = "blocked"
        else:
            user_to_manage.is_active = True
            action = "unblocked"

        user_to_manage.save()

        messages.success(
            request, f"User {user_to_manage.username} has been successfully {action}."
        )

        referer = request.META.get("HTTP_REFERER")

        if referer and f"/users/{user_id}/" in referer:
            return redirect("user_detail", user_id=user_id)

        return redirect("user_management")

    return render(
        request, "admin_panel/confirm_block.html", {"user_to_manage": user_to_manage}
    )
