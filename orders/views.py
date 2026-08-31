from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from .models import Order, OrderItem, OrderStatusHistory
from django.http import HttpResponse
from weasyprint import HTML
from wallets.models import Wallet, WalletTransaction
from django.template.loader import render_to_string
from django.db.models import Count
from decimal import Decimal, ROUND_HALF_UP
from django.core.paginator import Paginator
from django.db.models import Count, F
# Maps order_status -> step index used by the horizontal tracking stepper
# in the template. Statuses not in this dict (CANCELLED, RETURN_REQUESTED,
# RETURNED, RETURN_REJECTED) are handled separately in the template, since
# they branch off the main PENDING -> DELIVERED flow rather than sitting on it.
ORDER_STATUS_STEPS = {
    "PENDING": 0,
    "CONFIRMED": 1,
    "SHIPPED": 2,
    "OUT_FOR_DELIVERY": 3,
    "DELIVERED": 4,
}


def record_status_change(order, status, note=""):
    """
    Logs a timestamped OrderStatusHistory row every time an order's
    status changes. Call this immediately after setting
    order.order_status = "..." and saving the order.

    Guards against creating a duplicate row if the latest history
    entry already matches the status being recorded (e.g. if a view
    is somehow triggered twice for the same transition).
    """
    last = order.status_history.order_by("-changed_at").first()
    if last and last.status == status:
        return
    OrderStatusHistory.objects.create(order=order, status=status, note=note)


@login_required
def order_list_view(request):

    search_query = request.GET.get("q", "")
    status_filter = request.GET.get("status", "ALL")

    orders = Order.objects.filter(
        user=request.user
    ).order_by("-created_at")

    if search_query:
        orders = orders.filter(
            order_id__icontains=search_query
        )

    if status_filter != "ALL":
        orders = orders.filter(
            order_status=status_filter
        )

    paginator = Paginator(orders, 5)

    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    current_page = page_obj.number
    total_pages = paginator.num_pages

    context = {
        "page_obj": page_obj,
        "search_query": search_query,
        "current_page": current_page,
        "total_pages": total_pages,

        "selected_status": status_filter,
    }

    return render(
        request,
        "orders/order_list.html",
        context,
    )


@login_required
def order_detail_view(request, order_id):

    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    # Backfill safety net: orders placed before this feature existed won't
    # have any OrderStatusHistory rows yet. Create one for their current
    # status on first view so the timeline is never empty. Harmless no-op
    # for orders that already have history.
    if not order.status_history.exists():
        OrderStatusHistory.objects.create(order=order, status=order.order_status)

    context = {
        "order": order,
        "status_history": order.status_history.all(),
        "step": ORDER_STATUS_STEPS.get(order.order_status, -1),
    }

    return render(request, "orders/order_detail.html", context)


@login_required
@transaction.atomic
def cancel_order_view(request, order_id):

    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    if order.order_status in ["SHIPPED", "DELIVERED", "CANCELLED"]:

        messages.error(request, "This order cannot be cancelled.")

        return redirect("order_detail", order.order_id)

    reason = request.POST.get("reason", "")

    # Store payment status before modifying order
    was_paid = order.payment_status == "PAID"

    order.order_status = "CANCELLED"
    order.cancellation_reason = reason

    # Online payment + Wallet refund handling
    if order.payment_method == "ONLINE" and was_paid:
        order.payment_status = "REFUNDED"

        # Refund to wallet
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        user_wallet = wallet
        refund_amount = order.total_amount

        # Update wallet balance
        user_wallet.balance += refund_amount
        user_wallet.save()

        # Create wallet transaction record
        WalletTransaction.objects.create(
            wallet=user_wallet,
            amount=refund_amount,
            transaction_type="CREDIT",
            purpose="REFUND",
            order_id=order.order_id,
            description=(
                f"Instant refund for cancellation of " f"Order #{order.order_id}"
            ),
        )

        messages.success(
            request, f"₹{refund_amount} has been credited back to your wallet."
        )

    elif order.payment_method == "ONLINE":
        order.payment_status = "FAILED"

    order.save()
    record_status_change(order, "CANCELLED", note=reason)

    for item in order.items.all():

        if item.item_status == "ACTIVE":

            item.item_status = "CANCELLED"
            item.cancellation_reason = reason
            item.save()

            variant = item.product_variant

            if variant:

                variant.stock += item.quantity
                variant.save()

    recalculate_order_totals(order)

    messages.success(request, "Order cancelled successfully and stock updated.")

    return redirect("order_detail", order.order_id)


@login_required
@transaction.atomic
def cancel_order_item_view(request, item_id):

    item = get_object_or_404(OrderItem, id=item_id, order__user=request.user)

    order = item.order

    if order.order_status in ["SHIPPED", "DELIVERED", "CANCELLED"]:
        messages.error(request, "This item cannot be cancelled.")
        return redirect("order_detail", order.order_id)

    if item.item_status != "ACTIVE":
        messages.error(request, "Item already cancelled.")
        return redirect("order_detail", order.order_id)

    reason = request.POST.get("reason", "")

    # Store values before cancellation
    item_refund_amount = calculate_item_refund(item)
    was_paid = order.payment_status == "PAID"

    item.item_status = "CANCELLED"
    item.cancellation_reason = reason
    item.save()

    variant = item.product_variant

    if variant:
        variant.stock += item.quantity
        variant.save()

    # Wallet refund for paid orders
    if was_paid:
        wallet, created = Wallet.objects.get_or_create(user=request.user)

        user_wallet = wallet

        user_wallet.balance += item_refund_amount
        user_wallet.save()

        WalletTransaction.objects.create(
            wallet=user_wallet,
            amount=item_refund_amount,
            transaction_type="CREDIT",
            purpose="REFUND",
            order_id=order.order_id,
            description=(
                f"Instant refund for item cancellation " f"from Order #{order.order_id}"
            ),
        )

        messages.success(
            request, f"₹{item_refund_amount} has been refunded to your wallet."
        )

    recalculate_order_totals(order)

    # If no active items remain, cancel entire order
    if not order.items.filter(item_status="ACTIVE").exists():

        order.order_status = "CANCELLED"

        if was_paid:
            order.payment_status = "REFUNDED"

        order.save()
        record_status_change(order, "CANCELLED", note=reason)

    messages.success(request, "Item cancelled successfully.")

    return redirect("order_detail", order.order_id)


@login_required
def return_order_view(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    if order.order_status != "DELIVERED":
        messages.error(request, "Only delivered orders can be returned.")
        return redirect("order_detail", order.order_id)

    reason = request.POST.get("reason")

    if not reason:
        messages.error(request, "Return reason is required.")
        return redirect("order_detail", order.order_id)

    order.order_status = "RETURN_REQUESTED"
    order.return_reason = reason
    order.save()
    record_status_change(order, "RETURN_REQUESTED", note=reason)

    # Mirror cancel: mark all active items too
    for item in order.items.filter(item_status="ACTIVE"):
        item.item_status = "RETURN_REQUESTED"
        item.return_reason = reason
        item.save()

    messages.success(request, "Return request submitted.")
    return redirect("order_detail", order.order_id)


@login_required
@transaction.atomic
def return_order_item_view(request, item_id):
    item = get_object_or_404(OrderItem, id=item_id, order__user=request.user)
    order = item.order

    if order.order_status != "DELIVERED":
        messages.error(request, "Only delivered orders can have items returned.")
        return redirect("order_detail", order.order_id)

    if item.item_status != "ACTIVE":
        messages.error(request, "This item is not eligible for return.")
        return redirect("order_detail", order.order_id)

    reason = request.POST.get("reason", "")

    if not reason:
        messages.error(request, "Return reason is required.")
        return redirect("order_detail", order.order_id)

    item.item_status = "RETURN_REQUESTED"
    item.return_reason = reason
    item.save()

    # If all active items are now return-requested, escalate the whole order
    active_items = order.items.filter(item_status="ACTIVE")
    if not active_items.exists():
        order.order_status = "RETURN_REQUESTED"
        order.save()
        record_status_change(order, "RETURN_REQUESTED", note=reason)

    messages.success(request, "Return request submitted for item.")
    return redirect("order_detail", order.order_id)

def get_item_coupon_share(item):
    """
    Returns this item's fixed share of the order's coupon discount.

    Uses the sum of ALL items' subtotal (regardless of current status) as
    the denominator — never order.subtotal, which shrinks every time an
    item is cancelled. Using a shrinking denominator here was the actual
    bug: it made each subsequent cancellation claim a bigger slice of the
    same coupon, effectively re-applying it multiple times. item.subtotal
    itself is never mutated by cancel/return logic, making it — and the
    sum across all items — a stable, order-placement-time baseline.
    """
    order = item.order

    if not order.coupon_discount:
        return Decimal("0.00")

    total_items_subtotal = sum(i.subtotal for i in order.items.all())
    if not total_items_subtotal:
        return Decimal("0.00")

    share = (item.subtotal / total_items_subtotal) * order.coupon_discount
    share = min(share, item.subtotal)  # never deduct more than the item is worth
    return share.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_item_refund(item):
    """
    Refund amount for cancelling/returning a single item: its subtotal
    minus its fixed proportional share of the order's coupon discount.
    """
    return item.subtotal - get_item_coupon_share(item)

def recalculate_order_totals(order):
    active_items = order.items.filter(item_status="ACTIVE")

    if not active_items.exists():
        # Nothing left active — preserve existing totals as the historical
        # record of what was actually charged, rather than collapsing
        # subtotal/total_amount to ~0.
        return

    subtotal = sum(item.subtotal for item in active_items)
    discount = sum(
        (item.price * item.quantity) - item.subtotal for item in active_items
    )

    # Sum each active item's OWN fixed coupon share — never re-derive this
    # from order.coupon_discount directly, and never mutate
    # order.coupon_discount itself. That field stays frozen as the
    # original, full discount given at checkout (sales reports and
    # invoices depend on that historical figure being stable).
    active_coupon_share = sum(get_item_coupon_share(item) for item in active_items)

    order.subtotal = subtotal
    order.discount = discount
    order.total_amount = (subtotal + order.shipping_charge) - active_coupon_share
    order.save()


@login_required
def download_invoice_view(request, order_id):

    order = get_object_or_404(
        Order.objects.prefetch_related("items"),
        order_id=order_id,
        user=request.user,
    )

    active_items = order.items.filter(item_status="ACTIVE")

    context = {
        "order": order,
        "items": active_items,
    }

    html_string = render_to_string(
        "orders/invoice.html",
        context,
    )

    pdf_file = HTML(
        string=html_string, base_url=request.build_absolute_uri("/")
    ).write_pdf()

    response = HttpResponse(pdf_file, content_type="application/pdf")

    response["Content-Disposition"] = (
        f'attachment; filename="invoice-{order.order_id}.pdf"'
    )

    return response


@login_required
@transaction.atomic
def admin_approve_return_view(request, order_id):
    """
    Administrative endpoint to approve a returned order.
    Fulfills requirement (b): Refund to wallet after admin confirmation.
    """
    # Guard clause: Ensure only staff can access this action
    if not request.user.is_staff:
        messages.error(request, "Unauthorized access.")
        return redirect("order_detail", order_id)

    order = get_object_or_404(Order, order_id=order_id)

    if order.order_status != "RETURN_REQUESTED":
        messages.error(request, "This order is not pending a return approval.")
        return redirect("order_detail", order.order_id)

    # Process the wallet credit
    order.order_status = "RETURNED"
    order.payment_status = "REFUNDED"
    order.save()
    record_status_change(order, "RETURNED")

    # Get user wallet and execute transaction
    user_wallet, created = Wallet.objects.get_or_create(
    user=order.user
)
    refund_amount = order.total_amount

    user_wallet.balance += refund_amount
    user_wallet.save()

    WalletTransaction.objects.create(
        wallet=user_wallet,
        amount=refund_amount,
        transaction_type="CREDIT",
        purpose="REFUND",
        order_id=order.order_id,
        description=f"Admin-approved refund for returned Order #{order.order_id}",
    )

    # Update item statuses to complete the audit trail
    for item in order.items.filter(item_status="RETURN_REQUESTED"):
        item.item_status = "RETURNED"
        item.save()
        if item.product_variant:
            ProductVariant.objects.filter(id=item.product_variant.id).update(
            stock=F("stock") + item.quantity
        )
    

    messages.success(
        request,
        f"Return approved. ₹{refund_amount} has been safely credited to {order.user.username}'s wallet.",
    )
    return redirect("order_detail", order.order_id)


# ============================================================
# WHEN YOU BUILD AN ADMIN VIEW THAT MOVES ORDERS THROUGH
# PENDING -> CONFIRMED -> SHIPPED -> OUT_FOR_DELIVERY -> DELIVERED,
# follow this exact pattern so the tracking timeline picks it up:
#
#     order.order_status = new_status
#     order.save()
#     record_status_change(order, new_status, note=optional_note)
#     return redirect("order_detail", order.order_id)
# ============================================================