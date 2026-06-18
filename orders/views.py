from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from .models import Order, OrderItem
from django.http import HttpResponse
from weasyprint import HTML
from wallets.models import Wallet, WalletTransaction
from django.template.loader import render_to_string


from django.core.paginator import Paginator

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

    context = {"order": order}

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
    item_refund_amount = item.subtotal
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

    messages.success(request, "Return request submitted for item.")
    return redirect("order_detail", order.order_id)


def recalculate_order_totals(order):
    active_items = order.items.filter(item_status="ACTIVE")
    subtotal = sum(item.subtotal for item in active_items)
    discount = sum(
        (item.price * item.quantity) - item.subtotal for item in active_items
    )

    # Preserve the coupon discount, but never let it exceed the remaining
    # subtotal (e.g. after cancelling items, a discount that applied to the
    # original cart may no longer make sense against a smaller total).
    coupon_discount = order.coupon_discount or 0
    if coupon_discount > subtotal:
        coupon_discount = subtotal
        order.coupon_discount = coupon_discount

    order.subtotal = subtotal
    order.discount = discount
    order.total_amount = (subtotal + order.shipping_charge) - coupon_discount
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

    messages.success(
        request,
        f"Return approved. ₹{refund_amount} has been safely credited to {order.user.username}'s wallet.",
    )
    return redirect("order_detail", order.order_id)
