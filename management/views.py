from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Q, F
from django.contrib import messages
from orders.models import Order
from products.models import ProductVariant
from django.db import transaction
from orders.views import recalculate_order_totals
from orders.models import Order, OrderItem
from wallets.models import Wallet, WalletTransaction
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum, Count
from django.http import HttpResponse
from openpyxl import Workbook
from weasyprint import HTML
from django.template.loader import render_to_string


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

    context = {
        "orders": page_obj,
        "search_query": search_query,
        "status_filter": status_filter,
        "status_choices": Order.ORDER_STATUS,
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

    # -----------------------------
    # 1. ALLOWED STATUS FLOW RULES
    # -----------------------------
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

    context = {
        "variants": page_obj,
        "search_query": search_query,
        "stock_filter": stock_filter,
        "sort": sort,
    }
    return render(request, "management/inventory_list.html", context)


def sync_order_status(order):
    items = order.items.all()

    if items.filter(item_status="RETURN_REQUESTED").exists():
        order.order_status = "RETURN_REQUESTED"

    elif items.filter(item_status="RETURNED").count() == items.count():
        order.order_status = "RETURNED"

    elif items.filter(item_status="CANCELLED").count() == items.count():
        order.order_status = "CANCELLED"

    elif items.filter(item_status="ACTIVE").exists():
        order.order_status = "CONFIRMED"

    order.save()


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

        if variant:
            ProductVariant.objects.filter(id=variant.id).update(
                stock=F("stock") - item.quantity
            )

        item.item_status = "ACTIVE"
        item.save()

        messages.success(request, "Item reactivated successfully.")
        return redirect("management:admin_order_detail", item.order.order_id)

    messages.error(request, "Invalid item status transition.")
    return redirect("management:admin_order_detail", item.order.order_id)


@staff_member_required
def admin_return_requests(request):
    # 1. Base query: Capture ALL items that belong to a return process workflow
    return_statuses = ["RETURN_REQUESTED", "RETURNED", "RETURN_REJECTED"]
    items = (
        OrderItem.objects.filter(item_status__in=return_statuses)
        .select_related("order", "order__user", "product_variant")
        .order_by("-created_at")
    )

    # 2. Extract and Handle Filters
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

    # 3. Add Pagination (8 entries per page matches your theme standard)
    paginator = Paginator(items, 8)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # 4. Generate explicit Return Choices dynamically for your template's select box
    # This filters down OrderItem choices specifically to your valid return workflows
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

    # Check remaining non-returned active products to update complete parent order state
    remaining_items = item.order.items.exclude(
        item_status__in=["RETURNED", "CANCELLED"]
    )

    if not remaining_items.exists():
        item.order.order_status = "RETURNED"
        item.order.payment_status = "REFUNDED"
        item.order.save()

    wallet.balance += item.subtotal
    wallet.save()

    WalletTransaction.objects.create(
        wallet=wallet,
        amount=item.subtotal,
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

    return redirect("management:admin_return_request_detail", item_id=item.id)


# In your views.py, look at this specific function and change it:
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

    total_refund = 0

    for item in order.items.all():

        if item.item_status == "RETURN_REQUESTED":

            item.item_status = "RETURNED"
            item.save()

            if item.product_variant:
                ProductVariant.objects.filter(id=item.product_variant.id).update(
                    stock=F("stock") + item.quantity
                )

            total_refund += item.subtotal

    wallet, _ = Wallet.objects.get_or_create(user=order.user)
    wallet.balance += total_refund
    wallet.save()

    WalletTransaction.objects.create(
        wallet=wallet,
        amount=total_refund,
        transaction_type="CREDIT",
        purpose="FULL_ORDER_REFUND",
        order_id=order.order_id,
        description="Full order return refund",
    )

    order.order_status = "RETURNED"
    order.payment_status = "REFUNDED"
    order.save()

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

    messages.success(request, "Full order return rejected.")

    return redirect("management:admin_order_detail", order_id=order_id)


def admin_transactions_list(request):
    qs = WalletTransaction.objects.select_related("wallet__user").order_by(
        "-created_at"
    )

    search = request.GET.get("search", "").strip()
    type_filter = request.GET.get("transaction_type", "")
    purpose_filter = request.GET.get("purpose", "")

    if search:
        qs = qs.filter(
            Q(wallet__user__email__icontains=search)
            | Q(wallet__user__username__icontains=search)
            | Q(razorpay_payment_id__icontains=search)
            | Q(order_id__icontains=search)
        )

    if type_filter:
        qs = qs.filter(transaction_type=type_filter)

    if purpose_filter == "RECHARGE":
        qs = qs.filter(purpose="RECHARGE")
    elif purpose_filter == "PURCHASE":
        qs = qs.filter(purpose="PURCHASE")
    elif purpose_filter == "ADMIN_ADJUST":
        qs = qs.filter(purpose="ADMIN_ADJUST")
    elif purpose_filter == "REFUND_ORDER":
        qs = qs.filter(purpose="REFUND", description__icontains="cancellation of")
    elif purpose_filter == "REFUND_ITEM":
        qs = qs.filter(purpose="REFUND", description__icontains="item cancellation")
    elif purpose_filter == "REFUND_RETURN":
        qs = qs.filter(purpose="REFUND", description__icontains="returned")

    paginator = Paginator(qs, 10)
    page = paginator.get_page(request.GET.get("page"))

    # Custom purpose choices for dropdown — replaces model choices
    purpose_choices = [
        ("RECHARGE", "Wallet Recharge"),
        ("PURCHASE", "Order Payment"),
        ("REFUND_ORDER", "Order Cancel Refund"),
        ("REFUND_ITEM", "Item Cancel Refund"),
        ("REFUND_RETURN", "Return Refund"),
        ("ADMIN_ADJUST", "Admin Adjustment"),
    ]

    return render(
        request,
        "management/admin_transactions_list.html",
        {
            "transactions": page,
            "search_query": search,
            "type_filter": type_filter,
            "purpose_filter": purpose_filter,
            "type_choices": WalletTransaction.TRANSACTION_TYPE,
            "purpose_choices": purpose_choices,
        },
    )


def admin_transaction_detail(request, pk):
    txn = get_object_or_404(
        WalletTransaction.objects.select_related("wallet__user"), pk=pk
    )
    return render(
        request,
        "management/admin_transaction_detail.html",
        {
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

    context = {
        "orders": orders,
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
            orders = orders.filter(
                created_at__date__range=[start_date, end_date]
            )

    # Summary calculations

    total_orders = orders.count()

    total_sales = (
        orders.aggregate(total=Sum("total_amount"))["total"]
        or 0
    )

    total_product_discount = (
        orders.aggregate(total=Sum("discount"))["total"]
        or 0
    )

    total_coupon_discount = (
        orders.aggregate(total=Sum("coupon_discount"))["total"]
        or 0
    )

    total_discount = (
        total_product_discount +
        total_coupon_discount
    )

    net_revenue = (
        total_sales -
        total_product_discount -
        total_coupon_discount
    )

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

    response["Content-Disposition"] = (
        'attachment; filename="sales_report.pdf"'
    )

    return response


