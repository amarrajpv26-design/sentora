from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from .models import Order, OrderItem
from django.http import HttpResponse
from weasyprint import HTML
from django.template.loader import render_to_string



@login_required
def order_list_view(request):

    search_query = request.GET.get("q", "")

    orders = Order.objects.filter(user=request.user)

    if search_query:

        orders = orders.filter(order_id__icontains=search_query)

    context = {
        "orders": orders,
        "search_query": search_query,
    }

    return render(request, "orders/order_list.html", context)


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

    order.order_status = "CANCELLED"

    order.cancellation_reason = reason

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

    messages.success(request, "Order cancelled successfully.")

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
    item.item_status = "CANCELLED"
    item.cancellation_reason = reason
    item.save()

    variant = item.product_variant
    if variant:
        variant.stock += item.quantity
        variant.save()

    recalculate_order_totals(order)

    if not order.items.filter(item_status="ACTIVE").exists():
        order.order_status = "CANCELLED"
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
        order.return_reason = "All items return requested"
        order.save()

    messages.success(request, "Return request submitted for item.")
    return redirect("order_detail", order.order_id)


def recalculate_order_totals(order):
    active_items = order.items.filter(item_status="ACTIVE")
    subtotal = sum(item.subtotal for item in active_items)
    discount = sum(
        (item.price * item.quantity) - item.subtotal for item in active_items
    )
    order.subtotal = subtotal
    order.discount = discount
    order.total_amount = subtotal + order.shipping_charge
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
        string=html_string,
        base_url=request.build_absolute_uri("/")
    ).write_pdf()

    response = HttpResponse(
        pdf_file,
        content_type="application/pdf"
    )

    response["Content-Disposition"] = (
        f'attachment; filename="invoice-{order.order_id}.pdf"'
    )

    return response