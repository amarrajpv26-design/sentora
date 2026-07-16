from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Q, F
from django.contrib import messages
from orders.models import Order
from products.models import ProductVariant
from django.db import transaction
from orders.views import (
    recalculate_order_totals,
    record_status_change,
    calculate_item_refund,
)
from orders.models import Order, OrderItem
from wallets.models import Wallet, WalletTransaction
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, Count
from django.http import HttpResponse
from openpyxl import Workbook
from weasyprint import HTML
from django.template.loader import render_to_string
from itertools import chain  # only if not already there


@staff_member_required(login_url="user_login")
def admin_orders_list(request):

    orders = Order.objects.all().order_by("-created_at")

    search_query = request.GET.get("search", "").strip()
    if search_query:
        orders = orders.filter(
            Q(order_id__icontains=search_query)
            | Q(full_name__icontains=search_query)
            | Q(user__email__icontains=search_query)
        )

    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        orders = orders.filter(order_status=status_filter)

    paginator = Paginator(orders, 8)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    status_counts_qs = Order.objects.values("order_status").annotate(count=Count("id"))
    status_counts = {row["order_status"]: row["count"] for row in status_counts_qs}
    total_orders_count = Order.objects.count()

    context = {
        "orders": page_obj,
        "search_query": search_query,
        "status_filter": status_filter,
        "status_choices": Order.ORDER_STATUS,
        "status_counts": status_counts,  # <-- NEW
        "total_orders_count": total_orders_count,  # <-- NEW
    }
    return render(request, "management/orders_list.html", context)


@staff_member_required(login_url="user_login")
def admin_order_detail(request, order_id):

    order = get_object_or_404(Order, order_id=order_id)
    items = order.items.all()
    return render(
        request, "management/order_detail.html", {"order": order, "items": items}
    )


@staff_member_required(login_url="user_login")
@transaction.atomic
def change_order_status(request, order_id):

    if request.method != "POST":
        return redirect("management:admin_orders_list")

    order = get_object_or_404(Order, order_id=order_id)

    new_status = request.POST.get("order_status")
    old_status = order.order_status

    ALLOWED_TRANSITIONS = {
        "PENDING": ["CONFIRMED", "CANCELLED"],
        "CONFIRMED": ["SHIPPED", "CANCELLED"],
        "SHIPPED": ["OUT_FOR_DELIVERY"],
        "OUT_FOR_DELIVERY": ["DELIVERED"],
        "DELIVERED": ["RETURN_REQUESTED"],
        "RETURN_REQUESTED": [],  # handled via item approval
        "RETURNED": [],
        "CANCELLED": [],
    }

    if new_status not in dict(Order.ORDER_STATUS):
        messages.error(request, "Invalid status selected.")
        return redirect("management:admin_order_detail", order_id=order.order_id)

    # -----------------------------
    # 2. BLOCK INVALID TRANSITIONS
    # -----------------------------
    if new_status not in ALLOWED_TRANSITIONS.get(old_status, []):
        messages.error(request, f"Cannot change from {old_status} to {new_status}.")
        return redirect("management:admin_order_detail", order_id=order.order_id)

    # -----------------------------
    # 3. CANCEL ORDER → RESTOCK ITEMS
    # -----------------------------
    if new_status == "CANCELLED":

        for item in order.items.select_related("product_variant").all():

            if item.item_status == "ACTIVE" and item.product_variant:

                ProductVariant.objects.filter(id=item.product_variant.id).update(
                    stock=F("stock") + item.quantity
                )

                item.item_status = "CANCELLED"
                item.save()

        recalculate_order_totals(order)

    # -----------------------------
    # 4. NORMAL STATUS UPDATE
    # -----------------------------
    order.order_status = new_status
    if new_status == "DELIVERED":
        if order.payment_method == "COD":
            order.payment_status = "PAID"
    elif new_status in ("CONFIRMED", "SHIPPED", "OUT_FOR_DELIVERY"):
        order.items.exclude(
            item_status__in=[
                "CANCELLED",
                "RETURN_REQUESTED",
                "RETURNED",
                "RETURN_REJECTED",
            ]
        ).update(item_status="ACTIVE")

    order.save()
    record_status_change(order, new_status, note=f"Updated by admin from {old_status}")

    messages.success(request, f"Order updated to {order.get_order_status_display()}.")

    return redirect("management:admin_order_detail", order_id=order.order_id)


@staff_member_required(login_url="user_login")
def admin_inventory_list(request):

    variants = ProductVariant.objects.select_related("product", "product__brand").all()

    search_query = request.GET.get("search", "").strip()
    if search_query:
        variants = variants.filter(
            Q(size__icontains=search_query)
            | Q(product__name__icontains=search_query)
            | Q(product__brand__name__icontains=search_query)
        )

    stock_filter = request.GET.get("stock_status", "").strip()

    if stock_filter == "abundant":
        variants = variants.filter(stock__gt=5)

    elif stock_filter == "low":
        variants = variants.filter(stock__lte=5, stock__gt=0)

    elif stock_filter == "out":
        variants = variants.filter(stock=0)

    sort = request.GET.get("sort", "product_name")
    if sort == "stock_low":
        variants = variants.order_by("stock")

    elif sort == "stock_high":
        variants = variants.order_by("-stock")
    else:
        variants = variants.order_by("product__name")

    paginator = Paginator(variants, 8)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # NEW: stock breakdown counts, computed from the FULL unfiltered table
    all_variants = ProductVariant.objects.all()
    stock_counts = {
        "in_stock": all_variants.filter(stock__gt=5).count(),
        "low_stock": all_variants.filter(stock__lte=5, stock__gt=0).count(),
        "out_of_stock": all_variants.filter(stock=0).count(),
        "total": all_variants.count(),
    }

    context = {
        "variants": page_obj,
        "search_query": search_query,
        "stock_filter": stock_filter,
        "sort": sort,
        "stock_counts": stock_counts,  # <-- NEW
    }
    return render(request, "management/inventory_list.html", context)


def sync_order_status(order):
    items = order.items.all()

    old_status = order.order_status

    if items.filter(item_status="RETURN_REQUESTED").exists():
        order.order_status = "RETURN_REQUESTED"

    elif items.filter(item_status="RETURNED").count() == items.count():
        order.order_status = "RETURNED"

    elif items.filter(item_status="CANCELLED").count() == items.count():
        order.order_status = "CANCELLED"

    elif items.filter(item_status="ACTIVE").exists():
        order.order_status = "CONFIRMED"

    order.save()

    if order.order_status != old_status:
        record_status_change(
            order, order.order_status, note="Auto-synced from item statuses"
        )


@staff_member_required(login_url="user_login")
def update_variant_stock(request, variant_id):
    """Updates stock inventory levels instantly via dashboard inputs"""

    if request.method == "POST":
        variant = get_object_or_404(ProductVariant, id=variant_id)

        try:
            new_stock = int(request.POST.get("stock", 0))

            if new_stock >= 0:
                variant.stock = new_stock
                variant.save()

                messages.success(
                    request,
                    f"Stock updated successfully for {variant.product.name} ({variant.size}).",
                )

            else:
                messages.error(
                    request, "Stock totals cannot register as less than zero."
                )

        except (ValueError, TypeError):
            messages.error(request, "Invalid numeric input entered.")

    return redirect(request.META.get("HTTP_REFERER", "management:admin_inventory_list"))


@staff_member_required(login_url="user_login")
@transaction.atomic
def handle_item_status_change(request, item_id):

    if request.method != "POST":
        return redirect("management:admin_orders_list")

    item = get_object_or_404(OrderItem, id=item_id)
    order = item.order
    new_status = request.POST.get("item_status")
    old_status = item.item_status

    # BLOCK invalid manual return workflow changes
    if old_status == "RETURN_REQUESTED":
        messages.error(
            request, "Return requests must be handled via Approve / Reject actions."
        )
        return redirect("management:admin_order_detail", item.order.order_id)

    if new_status == old_status:
        return redirect("management:admin_order_detail", item.order.order_id)

    # -------------------------
    # CANCEL ITEM
    # -------------------------
    if new_status == "CANCELLED" and old_status == "ACTIVE":

        if item.product_variant:
            ProductVariant.objects.filter(id=item.product_variant.id).update(
                stock=F("stock") + item.quantity
            )

        item.item_status = "CANCELLED"
        item.save()

        if order.payment_status == "PAID":
            refund_amount = calculate_item_refund(item)

            wallet, _ = Wallet.objects.get_or_create(user=order.user)
            wallet.balance += refund_amount
            wallet.save()

            WalletTransaction.objects.create(
                wallet=wallet,
                amount=refund_amount,
                transaction_type="CREDIT",
                purpose="REFUND",
                order_id=order.order_id,
                description=f"Admin cancelled item refund: {item.product_name} (Order #{order.order_id})",
            )

        recalculate_order_totals(order)

        # If no active items remain, cancel the whole order too
        if not order.items.filter(item_status="ACTIVE").exists():
            order.order_status = "CANCELLED"
            if order.payment_status == "PAID":
                order.payment_status = "REFUNDED"
            order.save()
            record_status_change(
                order,
                "CANCELLED",
                note="Auto-cancelled: last active item cancelled by admin",
            )

        messages.success(request, "Item cancelled successfully.")
        return redirect("management:admin_order_detail", item.order.order_id)

    # -------------------------
    # RE-ACTIVATE ITEM (optional safe recovery)
    # -------------------------
    if new_status == "ACTIVE" and old_status == "CANCELLED":

        variant = item.product_variant

        if variant and variant.stock < item.quantity:
            messages.error(request, "Insufficient stock to reactivate item.")
            return redirect("management:admin_order_detail", item.order.order_id)

        if order.payment_status in ("PAID", "REFUNDED"):
            refund_amount = calculate_item_refund(item)
            wallet, _ = Wallet.objects.get_or_create(user=order.user)

            if wallet.balance < refund_amount:
                messages.error(
                    request,
                    "Cannot reactivate: customer's wallet balance is lower than the refunded amount.",
                )
                return redirect("management:admin_order_detail", item.order.order_id)

            wallet.balance -= refund_amount
            wallet.save()

            WalletTransaction.objects.create(
                wallet=wallet,
                amount=refund_amount,
                transaction_type="DEBIT",
                purpose="REFUND_REVERSAL",
                order_id=order.order_id,
                description=f"Reversed refund: item reactivated by admin: {item.product_name} (Order #{order.order_id})",
            )

        if variant:
            ProductVariant.objects.filter(id=variant.id).update(
                stock=F("stock") - item.quantity
            )

        item.item_status = "ACTIVE"
        item.save()

        if order.order_status == "CANCELLED":
            order.order_status = "CONFIRMED"
            if order.payment_status == "REFUNDED":
                order.payment_status = "PAID"
            order.save()
            record_status_change(
                order, "CONFIRMED", note="Re-activated: item restored by admin"
            )

        recalculate_order_totals(order)

        messages.success(request, "Item reactivated successfully.")
        return redirect("management:admin_order_detail", item.order.order_id)

    messages.error(request, "Invalid item status transition.")
    return redirect("management:admin_order_detail", item.order.order_id)


@staff_member_required
def admin_return_requests(request):

    return_statuses = ["RETURN_REQUESTED", "RETURNED", "RETURN_REJECTED"]
    items = (
        OrderItem.objects.filter(item_status__in=return_statuses)
        .select_related("order", "order__user", "product_variant")
        .order_by("-created_at")
    )

    search_query = request.GET.get("search", "").strip()
    status_filter = request.GET.get("status", "").strip()

    if search_query:
        items = items.filter(
            Q(order__order_id__icontains=search_query)
            | Q(product_name__icontains=search_query)
            | Q(order__full_name__icontains=search_query)
            | Q(order__user__email__icontains=search_query)
        )

    if status_filter:
        items = items.filter(item_status=status_filter)

    paginator = Paginator(items, 8)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return_status_choices = [
        ("RETURN_REQUESTED", "Return Requested"),
        ("RETURNED", "Returned (Approved)"),
        ("RETURN_REJECTED", "Return Rejected"),
    ]

    context = {
        "items": page_obj,  # This passes the paginated object to the table loop
        "search_query": search_query,
        "status_filter": status_filter,
        "status_choices": return_status_choices,
    }

    return render(request, "management/return_requests.html", context)


@staff_member_required
@transaction.atomic
def approve_return_item(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)

    if item.item_status != "RETURN_REQUESTED":
        messages.error(request, "Invalid return request state.")
        return redirect("management:admin_return_request_detail", item_id=item.id)

    note = request.POST.get("admin_note", "")

    item.item_status = "RETURNED"
    item.admin_return_note = note
    item.save()

    variant = item.product_variant
    if variant:
        variant.stock += item.quantity
        variant.save()

    wallet, created = Wallet.objects.get_or_create(user=item.order.user)

    remaining_items = item.order.items.exclude(
        item_status__in=["RETURNED", "CANCELLED"]
    )

    if not remaining_items.exists():
        item.order.order_status = "RETURNED"
        item.order.payment_status = "REFUNDED"
        item.order.save()
        record_status_change(
            item.order,
            "RETURNED",
            note=f"All items returned (item #{item.id} approved)",
        )

    refund_amount = calculate_item_refund(item)

    wallet.balance += refund_amount
    wallet.save()

    WalletTransaction.objects.create(
        wallet=wallet,
        amount=refund_amount,
        transaction_type="CREDIT",
        purpose="REFUND",
        order_id=item.order.order_id,
        description=f"Refund for returned item: {item.product_name}",
    )

    messages.success(
        request,
        f"Return tracking item #{item.id} approved successfully. Funds returned to user wallet.",
    )
    return redirect("management:admin_return_request_detail", item_id=item.id)


@staff_member_required
@transaction.atomic
def reject_return_item(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id)

    if item.item_status != "RETURN_REQUESTED":
        messages.error(request, "Invalid return request state.")
        return redirect("management:admin_return_request_detail", item_id=item.id)

    note = request.POST.get("admin_note", "")
    if not note.strip():
        messages.error(
            request, "Rejection note is required to refuse an execution request."
        )
        return redirect("management:admin_return_request_detail", item_id=item.id)

    item.item_status = "RETURN_REJECTED"
    item.admin_return_note = note
    item.save()

    messages.success(request, "Return request has been safely rejected and logged.")

    order = item.order
    pending_requests = order.items.filter(item_status="RETURN_REQUESTED")
    if not pending_requests.exists():
        # Fall back gracefully to original standard delivery state
        order.order_status = "DELIVERED"
        order.save()
        record_status_change(
            order, "DELIVERED", note=f"Return rejected for item #{item.id}"
        )

    return redirect("management:admin_return_request_detail", item_id=item.id)


@staff_member_required
def admin_return_request_detail(request, item_id):
    # CHANGE item_status="RETURN_REQUESTED" to an __in lookup or remove the raw state requirement
    item = get_object_or_404(
        OrderItem.objects.select_related("order", "order__user", "product_variant"),
        id=item_id,
        item_status__in=["RETURN_REQUESTED", "RETURNED", "RETURN_REJECTED"],
    )

    return render(
        request,
        "management/return_request_detail.html",
        {
            "item": item,
            "order": item.order,
        },
    )


@staff_member_required
@transaction.atomic
def approve_full_return(request, order_id):

    order = get_object_or_404(Order, order_id=order_id)

    if order.order_status != "RETURN_REQUESTED":
        messages.error(request, "Invalid return state.")
        return redirect("management:admin_order_detail", order_id=order_id)

    refund_amount = order.total_amount

    for item in order.items.all():

        if item.item_status == "RETURN_REQUESTED":

            item.item_status = "RETURNED"
            item.save()

            if item.product_variant:
                ProductVariant.objects.filter(id=item.product_variant.id).update(
                    stock=F("stock") + item.quantity
                )

    wallet, _ = Wallet.objects.get_or_create(user=order.user)
    wallet.balance += refund_amount
    wallet.save()

    WalletTransaction.objects.create(
        wallet=wallet,
        amount=refund_amount,
        transaction_type="CREDIT",
        purpose="FULL_ORDER_REFUND",
        order_id=order.order_id,
        description="Full order return refund",
    )

    order.order_status = "RETURNED"
    order.payment_status = "REFUNDED"
    order.save()
    record_status_change(order, "RETURNED", note="Full order return approved by admin")

    messages.success(request, "Full order return approved.")

    return redirect("management:admin_order_detail", order_id=order_id)


@staff_member_required
@transaction.atomic
def reject_full_return(request, order_id):

    order = get_object_or_404(Order, order_id=order_id)

    if order.order_status != "RETURN_REQUESTED":
        messages.error(request, "Invalid return state.")
        return redirect("management:admin_order_detail", order_id=order_id)

    order.order_status = "DELIVERED"

    for item in order.items.filter(item_status="RETURN_REQUESTED"):
        item.item_status = "RETURN_REJECTED"
        item.save()

    order.save()
    record_status_change(order, "DELIVERED", note="Full order return rejected by admin")

    messages.success(request, "Full order return rejected.")

    return redirect("management:admin_order_detail", order_id=order_id)


def admin_transactions_list(request):
    """
    Unified ledger: merges WalletTransactions + Online (Razorpay) order payments
    into a single sorted, filterable list.
    """
    from itertools import chain

    search = request.GET.get("search", "").strip()
    type_filter = request.GET.get(
        "transaction_type", ""
    ).strip()  # CREDIT / DEBIT / ONLINE
    purpose_filter = request.GET.get("purpose", "").strip()

    # ── 1. WALLET TRANSACTIONS ────────────────────────────────
    wallet_qs = WalletTransaction.objects.select_related("wallet__user").order_by(
        "-created_at"
    )

    if search:
        wallet_qs = wallet_qs.filter(
            Q(wallet__user__email__icontains=search)
            | Q(wallet__user__username__icontains=search)
            | Q(razorpay_payment_id__icontains=search)
            | Q(order_id__icontains=search)
        )

    if type_filter == "CREDIT":
        wallet_qs = wallet_qs.filter(transaction_type="CREDIT")
    elif type_filter == "DEBIT":
        wallet_qs = wallet_qs.filter(transaction_type="DEBIT")
    elif type_filter == "ONLINE":
        wallet_qs = wallet_qs.none()  # online tab shows only order payments

    if purpose_filter == "RECHARGE":
        wallet_qs = wallet_qs.filter(purpose="RECHARGE")
    elif purpose_filter == "PURCHASE":
        wallet_qs = wallet_qs.filter(purpose="PURCHASE")
    elif purpose_filter == "REFERRAL":
        wallet_qs = wallet_qs.filter(purpose="REFERRAL_BONUS")
    elif purpose_filter == "REFUND_ORDER":
        wallet_qs = wallet_qs.filter(
            purpose="REFUND", description__icontains="cancellation of"
        )
    elif purpose_filter == "REFUND_ITEM":
        wallet_qs = wallet_qs.filter(
            purpose="REFUND", description__icontains="item cancellation"
        )
    elif purpose_filter == "REFUND_RETURN":
        wallet_qs = wallet_qs.filter(
            purpose="REFUND", description__icontains="returned"
        )
    elif purpose_filter == "ONLINE":
        wallet_qs = wallet_qs.none()

    # Normalise wallet rows into dicts
    wallet_rows = []
    for txn in wallet_qs:
        wallet_rows.append(
            {
                "source": "wallet",
                "pk": txn.pk,
                "date": txn.created_at,
                "user": txn.wallet.user,
                "amount": txn.amount,
                "type": txn.transaction_type,  # CREDIT / DEBIT
                "purpose": txn.purpose,
                "description": txn.description or "",
                "order_id": txn.order_id or "",
                "razorpay_id": txn.razorpay_payment_id or "",
                "raw": txn,
            }
        )

    # ── 2. ONLINE ORDER PAYMENTS (Razorpay) ──────────────────
    online_qs = (
        Order.objects.select_related("user")
        .filter(payment_method="ONLINE", payment_status="PAID")
        .exclude(razorpay_payment_id__isnull=True)
        .exclude(razorpay_payment_id="")
        .order_by("-created_at")
    )

    if search:
        online_qs = online_qs.filter(
            Q(user__email__icontains=search)
            | Q(user__username__icontains=search)
            | Q(razorpay_payment_id__icontains=search)
            | Q(order_id__icontains=search)
        )

    # Hide online rows when wallet-only type or wallet-only purpose is selected
    if type_filter in ("CREDIT", "DEBIT"):
        online_qs = online_qs.none()
    if purpose_filter and purpose_filter not in ("ONLINE", ""):
        online_qs = online_qs.none()

    online_rows = []
    for order in online_qs:
        online_rows.append(
            {
                "source": "online",
                "pk": order.pk,
                "date": order.created_at,
                "user": order.user,
                "amount": order.total_amount,
                "type": "ONLINE",
                "purpose": "ONLINE_PAYMENT",
                "description": f"Razorpay payment for Order #{order.order_id}",
                "order_id": order.order_id,
                "razorpay_id": order.razorpay_payment_id or "",
                "raw": order,
            }
        )

    # ── 3. MERGE + SORT ──────────────────────────────────────
    all_rows = sorted(
        chain(wallet_rows, online_rows),
        key=lambda r: r["date"],
        reverse=True,
    )

    # ── 4. PAGINATE ──────────────────────────────────────────
    paginator = Paginator(all_rows, 10)
    page = paginator.get_page(request.GET.get("page"))

    # ── 5. FILTER CHOICES FOR DROPDOWNS ──────────────────────
    type_choices = [
        ("", "All Types"),
        ("CREDIT", "Credit (Wallet In)"),
        ("DEBIT", "Debit (Wallet Out)"),
        ("ONLINE", "Online Payment (Razorpay)"),
    ]

    purpose_choices = [
        ("", "All Purposes"),
        ("ONLINE", "Online Payment"),
        ("RECHARGE", "Wallet Recharge"),
        ("PURCHASE", "Wallet Purchase"),
        ("REFUND_ORDER", "Order Cancel Refund"),
        ("REFUND_ITEM", "Item Cancel Refund"),
        ("REFUND_RETURN", "Return Refund"),
        ("REFERRAL", "Referral Bonus"),
    ]

    return render(
        request,
        "management/admin_transactions_list.html",
        {
            "transactions": page,
            "search_query": search,
            "type_filter": type_filter,
            "purpose_filter": purpose_filter,
            "type_choices": type_choices,
            "purpose_choices": purpose_choices,
        },
    )


def admin_transaction_detail(request, pk):

    source = request.GET.get("source", "wallet")

    if source == "online":
        order = get_object_or_404(Order.objects.select_related("user"), pk=pk)
        return render(
            request,
            "management/admin_transaction_detail.html",
            {
                "source": "online",
                "order": order,
            },
        )

    # Default: wallet transaction
    txn = get_object_or_404(
        WalletTransaction.objects.select_related("wallet__user"), pk=pk
    )
    return render(
        request,
        "management/admin_transaction_detail.html",
        {
            "source": "wallet",
            "txn": txn,
        },
    )


@staff_member_required(login_url="user_login")
def sales_report(request):

    report_type = request.GET.get("type", "daily")

    orders = (
        Order.objects.filter(payment_status="PAID")
        .exclude(order_status="CANCELLED")
        .order_by("-created_at")
    )

    today = timezone.now()

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    # -----------------------------
    # FILTER REPORT TYPE
    # -----------------------------
    if report_type == "daily":
        orders = orders.filter(created_at__date=today.date())

    elif report_type == "weekly":
        week_start = today - timedelta(days=7)
        orders = orders.filter(created_at__gte=week_start)

    elif report_type == "yearly":
        orders = orders.filter(created_at__year=today.year)

    elif report_type == "custom":
        if start_date and end_date:
            orders = orders.filter(created_at__date__range=[start_date, end_date])

    # -----------------------------
    # CALCULATIONS
    # -----------------------------
    total_orders = orders.count()

    total_sales = orders.aggregate(total=Sum("total_amount"))["total"] or 0

    total_product_discount = orders.aggregate(total=Sum("discount"))["total"] or 0

    total_coupon_discount = orders.aggregate(total=Sum("coupon_discount"))["total"] or 0

    total_discount = total_product_discount + total_coupon_discount

    net_revenue = total_sales - total_product_discount - total_coupon_discount

    paginator = Paginator(orders, 5)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "orders": page_obj,
        "report_type": report_type,
        "start_date": start_date,
        "end_date": end_date,
        "total_orders": total_orders,
        "total_sales": total_sales,
        "total_product_discount": total_product_discount,
        "total_coupon_discount": total_coupon_discount,
        "total_discount": total_discount,
        "net_revenue": net_revenue,
    }

    return render(
        request,
        "management/sales_report.html",
        context,
    )


def sales_report_pdf(request):

    report_type = request.GET.get("type", "daily")

    orders = (
        Order.objects.filter(payment_status="PAID")
        .exclude(order_status="CANCELLED")
        .order_by("-created_at")
    )

    today = timezone.now()

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")

    # Apply same filters as sales_report view

    if report_type == "daily":
        orders = orders.filter(created_at__date=today.date())

    elif report_type == "weekly":
        week_start = today - timedelta(days=7)
        orders = orders.filter(created_at__gte=week_start)

    elif report_type == "yearly":
        orders = orders.filter(created_at__year=today.year)

    elif report_type == "custom":
        if start_date and end_date:
            orders = orders.filter(created_at__date__range=[start_date, end_date])

    # Summary calculations

    total_orders = orders.count()

    total_sales = orders.aggregate(total=Sum("total_amount"))["total"] or 0

    total_product_discount = orders.aggregate(total=Sum("discount"))["total"] or 0

    total_coupon_discount = orders.aggregate(total=Sum("coupon_discount"))["total"] or 0

    total_discount = total_product_discount + total_coupon_discount

    net_revenue = total_sales - total_product_discount - total_coupon_discount

    context = {
        "orders": orders,
        "report_type": report_type.title(),
        "total_orders": total_orders,
        "total_sales": total_sales,
        "total_product_discount": total_product_discount,
        "total_coupon_discount": total_coupon_discount,
        "total_discount": total_discount,
        "net_revenue": net_revenue,
        "now": timezone.now(),
    }

    html_string = render_to_string(
        "management/sales_report_pdf.html",
        context,
    )

    pdf = HTML(string=html_string).write_pdf()

    response = HttpResponse(
        pdf,
        content_type="application/pdf",
    )

    response["Content-Disposition"] = 'attachment; filename="sales_report.pdf"'

    return response


@staff_member_required(login_url="user_login")
def admin_revenue_list(request):
    from django.db.models import Sum, Count, F, Q
    from django.utils import timezone
    from datetime import timedelta

    # ── Time filter ──────────────────────────────────────────
    filter_type = request.GET.get("filter", "all")
    start_date = request.GET.get("start_date", "")
    end_date = request.GET.get("end_date", "")
    sort_by = request.GET.get("sort", "revenue")  # revenue | units | orders
    view_type = request.GET.get("view", "product")  # product | category

    today = timezone.now()

    # Base: only paid, non-cancelled order items
    base_qs = OrderItem.objects.filter(
        order__payment_status="PAID",
    ).exclude(item_status="CANCELLED")

    if filter_type == "daily":
        base_qs = base_qs.filter(order__created_at__date=today.date())
    elif filter_type == "weekly":
        base_qs = base_qs.filter(order__created_at__gte=today - timedelta(days=7))
    elif filter_type == "monthly":
        base_qs = base_qs.filter(
            order__created_at__year=today.year,
            order__created_at__month=today.month,
        )
    elif filter_type == "yearly":
        base_qs = base_qs.filter(order__created_at__year=today.year)
    elif filter_type == "custom" and start_date and end_date:
        base_qs = base_qs.filter(order__created_at__date__range=[start_date, end_date])

    # ── Aggregate per product OR per category ────────────────
    if view_type == "category":
        # NOTE: products can belong to multiple categories (M2M), so a
        # single order item can contribute to more than one category's
        # totals here. This mirrors how the product list page already
        # handles categories — it is a deliberate "contribution" view,
        # not a strict partition of revenue.
        rows = (
            base_qs.values(
                "product_variant__product__categories__id",
                "product_variant__product__categories__name",
            )
            .annotate(
                total_revenue=Sum("subtotal"),
                total_units=Sum("quantity"),
                total_orders=Count("order", distinct=True),
            )
            .filter(product_variant__product__categories__id__isnull=False)
        )
    else:
        rows = (
            base_qs.values(
                "product_variant__product__id",
                "product_variant__product__name",
            )
            .annotate(
                total_revenue=Sum("subtotal"),
                total_units=Sum("quantity"),
                total_orders=Count("order", distinct=True),
            )
            .filter(product_variant__product__id__isnull=False)
        )

    # ── Sorting ──────────────────────────────────────────────
    if sort_by == "units":
        rows = rows.order_by("-total_units")
    elif sort_by == "orders":
        rows = rows.order_by("-total_orders")
    else:
        rows = rows.order_by("-total_revenue")

    # ── Totals for summary cards ─────────────────────────────
    totals = base_qs.aggregate(
        grand_revenue=Sum("subtotal"),
        grand_units=Sum("quantity"),
        grand_orders=Count("order", distinct=True),
    )

    # ── Refund total for the period ──────────────────────────
    refund_qs = WalletTransaction.objects.filter(
        transaction_type="CREDIT",
        purpose="REFUND",
    )
    if filter_type == "daily":
        refund_qs = refund_qs.filter(created_at__date=today.date())
    elif filter_type == "weekly":
        refund_qs = refund_qs.filter(created_at__gte=today - timedelta(days=7))
    elif filter_type == "monthly":
        refund_qs = refund_qs.filter(
            created_at__year=today.year, created_at__month=today.month
        )
    elif filter_type == "yearly":
        refund_qs = refund_qs.filter(created_at__year=today.year)
    elif filter_type == "custom" and start_date and end_date:
        refund_qs = refund_qs.filter(created_at__date__range=[start_date, end_date])

    total_refunds = refund_qs.aggregate(t=Sum("amount"))["t"] or 0

    # ── Paginate ─────────────────────────────────────────────
    paginator = Paginator(list(rows), 12)
    page_obj = paginator.get_page(request.GET.get("page"))

    # ── Period tabs for the filter form ───────────────────────
    # FIX: this was missing from context, which is why the time-filter
    # glass panel rendered as an empty box — the {% for key, label in
    # filter_tabs %} loop in the template had nothing to iterate over.
    filter_tabs = [
        ("all", "All Time"),
        ("daily", "Today"),
        ("weekly", "This Week"),
        ("monthly", "This Month"),
        ("yearly", "This Year"),
        ("custom", "Custom"),
    ]

    context = {
        "products": page_obj,  # kept name for template back-compat (product OR category rows)
        "totals": totals,
        "total_refunds": total_refunds,
        "filter_type": filter_type,
        "filter_tabs": filter_tabs,  # <-- NEW
        "start_date": start_date,
        "end_date": end_date,
        "sort_by": sort_by,
        "view_type": view_type,
    }
    return render(request, "management/revenue_list.html", context)


@staff_member_required(login_url="user_login")
def admin_revenue_product_detail(request, product_id):
    from django.db.models import Sum, Count, F, Q
    from products.models import Product

    product = get_object_or_404(Product, id=product_id)

    # ── All order items for this product ────────────────────
    all_items = (
        OrderItem.objects.filter(product_variant__product=product)
        .select_related("order", "order__user", "product_variant")
        .order_by("-order__created_at")
    )

    # ── Summary stats (NEVER affected by the table filters below —
    #    these always reflect the product's full history) ─────
    active_items = all_items.exclude(item_status__in=["CANCELLED"])

    paid_items = all_items.filter(order__payment_status="PAID").exclude(
        item_status="CANCELLED"
    )

    stats = {
        "total_revenue": paid_items.aggregate(t=Sum("subtotal"))["t"] or 0,
        "total_units_sold": paid_items.aggregate(t=Sum("quantity"))["t"] or 0,
        "total_orders": paid_items.aggregate(t=Count("order", distinct=True))["t"] or 0,
        "cancelled_units": all_items.filter(item_status="CANCELLED").aggregate(
            t=Sum("quantity")
        )["t"]
        or 0,
        "returned_units": all_items.filter(item_status__in=["RETURNED"]).aggregate(
            t=Sum("quantity")
        )["t"]
        or 0,
        "return_requested": all_items.filter(item_status="RETURN_REQUESTED").aggregate(
            t=Sum("quantity")
        )["t"]
        or 0,
        "refund_total": WalletTransaction.objects.filter(
            purpose="REFUND",
            order_id__in=all_items.values_list("order__order_id", flat=True),
        ).aggregate(t=Sum("amount"))["t"]
        or 0,
    }

    # Net revenue after refunds
    stats["net_revenue"] = stats["total_revenue"] - stats["refund_total"]

    # ── Per-variant breakdown (also unaffected by table filters) ─
    variant_breakdown = (
        paid_items.values("product_variant__id", "product_variant__size")
        .annotate(
            variant_revenue=Sum("subtotal"),
            variant_units=Sum("quantity"),
            variant_orders=Count("order", distinct=True),
        )
        .order_by("-variant_revenue")
    )

    # ── Order-level list (all statuses by default) ───────────
    order_rows = all_items.select_related("order__user", "product_variant").order_by(
        "-order__created_at"
    )

    # ── NEW: Order/Item status filters for the order history table ─
    order_status_filter = request.GET.get("order_status", "").strip()
    item_status_filter = request.GET.get("item_status", "").strip()

    if order_status_filter:
        order_rows = order_rows.filter(order__order_status=order_status_filter)

    if item_status_filter:
        order_rows = order_rows.filter(item_status=item_status_filter)

    paginator = Paginator(order_rows, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "product": product,
        "stats": stats,
        "variant_breakdown": variant_breakdown,
        "order_rows": page_obj,
        "order_status_filter": order_status_filter,  # <-- NEW
        "item_status_filter": item_status_filter,  # <-- NEW
        "order_status_choices": Order.ORDER_STATUS,  # <-- NEW: for the dropdown
        "item_status_choices": [  # <-- NEW: for the dropdown
            ("ACTIVE", "Active"),
            ("CANCELLED", "Cancelled"),
            ("RETURN_REQUESTED", "Return Requested"),
            ("RETURNED", "Returned"),
            ("RETURN_REJECTED", "Return Rejected"),
        ],
    }
    return render(request, "management/revenue_product_detail.html", context)


@staff_member_required(login_url="user_login")
def admin_revenue_category_detail(request, category_id):
    """
    Mirrors admin_revenue_product_detail, but rolled up at the category
    level. Shows every paid/active order item for products inside this
    category, plus a per-product breakdown (instead of per-variant).
    """
    from django.db.models import Sum, Count
    from products.models import Category

    category = get_object_or_404(Category, id=category_id)

    # ── All order items for products in this category ───────
    all_items = (
        OrderItem.objects.filter(product_variant__product__categories=category)
        .select_related(
            "order", "order__user", "product_variant", "product_variant__product"
        )
        .distinct()
        .order_by("-order__created_at")
    )

    paid_items = all_items.filter(order__payment_status="PAID").exclude(
        item_status="CANCELLED"
    )

    # ── Summary stats (NEVER affected by the table filters below —
    #    these always reflect the category's full history) ─────
    stats = {
        "total_revenue": paid_items.aggregate(t=Sum("subtotal"))["t"] or 0,
        "total_units_sold": paid_items.aggregate(t=Sum("quantity"))["t"] or 0,
        "total_orders": paid_items.aggregate(t=Count("order", distinct=True))["t"] or 0,
        "cancelled_units": all_items.filter(item_status="CANCELLED").aggregate(
            t=Sum("quantity")
        )["t"]
        or 0,
        "returned_units": all_items.filter(item_status__in=["RETURNED"]).aggregate(
            t=Sum("quantity")
        )["t"]
        or 0,
        "return_requested": all_items.filter(item_status="RETURN_REQUESTED").aggregate(
            t=Sum("quantity")
        )["t"]
        or 0,
        "refund_total": WalletTransaction.objects.filter(
            purpose="REFUND",
            order_id__in=all_items.values_list("order__order_id", flat=True).distinct(),
        ).aggregate(t=Sum("amount"))["t"]
        or 0,
    }

    stats["net_revenue"] = stats["total_revenue"] - stats["refund_total"]

    # ── Per-product breakdown within this category (also unaffected
    #    by the table filters below) ──────────────────────────
    product_breakdown = (
        paid_items.values(
            "product_variant__product__id",
            "product_variant__product__name",
        )
        .annotate(
            product_revenue=Sum("subtotal"),
            product_units=Sum("quantity"),
            product_orders=Count("order", distinct=True),
        )
        .order_by("-product_revenue")
    )

    # ── Order-level list (all statuses by default) ──────────
    order_rows = all_items.order_by("-order__created_at")

    # ── NEW: Order/Item status filters for the order history table ─
    order_status_filter = request.GET.get("order_status", "").strip()
    item_status_filter = request.GET.get("item_status", "").strip()

    if order_status_filter:
        order_rows = order_rows.filter(order__order_status=order_status_filter)

    if item_status_filter:
        order_rows = order_rows.filter(item_status=item_status_filter)

    paginator = Paginator(order_rows, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "category": category,
        "stats": stats,
        "product_breakdown": product_breakdown,
        "order_rows": page_obj,
        "order_status_filter": order_status_filter,  # <-- NEW
        "item_status_filter": item_status_filter,  # <-- NEW
        "order_status_choices": Order.ORDER_STATUS,  # <-- NEW: for the dropdown
        "item_status_choices": [  # <-- NEW: for the dropdown
            ("ACTIVE", "Active"),
            ("CANCELLED", "Cancelled"),
            ("RETURN_REQUESTED", "Return Requested"),
            ("RETURNED", "Returned"),
            ("RETURN_REJECTED", "Return Rejected"),
        ],
    }
    return render(request, "management/revenue_category_detail.html", context)
