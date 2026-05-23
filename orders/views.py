from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from .models import Order, OrderItem
from django.http import HttpResponse

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter


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

    # CANCEL ITEMS + RESTORE STOCK
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

    # RESTORE STOCK
    variant = item.product_variant
    if variant:
        variant.stock += item.quantity
        variant.save()

    # ALWAYS recalculate first
    recalculate_order_totals(order)

    # THEN check if all items cancelled
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


    messages.success(request, "Return request submitted.")

    return redirect("order_detail", order.order_id)

def recalculate_order_totals(order):

    active_items = order.items.filter(item_status="ACTIVE")

    # Recalculate subtotal from active items' selling price
    subtotal = sum(item.subtotal for item in active_items)

    # Recalculate discount from active items' (mrp - selling)
    discount = sum(
        (item.price * item.quantity) - item.subtotal
        for item in active_items
    )

    order.subtotal = subtotal
    order.discount = discount
    order.total_amount = subtotal + order.shipping_charge 

    order.save()


@login_required
def download_invoice_view(request, order_id):

    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    response = HttpResponse(content_type="application/pdf")

    response["Content-Disposition"] = f'attachment; filename="{order.order_id}.pdf"'

    doc = SimpleDocTemplate(response, pagesize=letter)

    styles = getSampleStyleSheet()

    elements = []

    # TITLE
    elements.append(Paragraph(f"Invoice - {order.order_id}", styles["Title"]))

    elements.append(Spacer(1, 20))

    # CUSTOMER
    elements.append(
        Paragraph(f"<b>Customer:</b> {order.full_name}", styles["BodyText"])
    )

    elements.append(
        Paragraph(f"<b>Phone:</b> {order.phone_number}", styles["BodyText"])
    )

    elements.append(
        Paragraph(
            f"<b>Address:</b> "
            f"{order.address_line_1}, "
            f"{order.city}, "
            f"{order.state} - "
            f"{order.pincode}",
            styles["BodyText"],
        )
    )

    elements.append(Spacer(1, 20))

    # TABLE DATA
    data = [["Product", "Qty", "Price", "Subtotal"]]

    for item in order.items.filter(item_status="ACTIVE"):

        data.append(
            [
                item.product_name,
                str(item.quantity),
                f"₹{item.price}",
                f"₹{item.subtotal}",
            ]
        )

    table = Table(data)

    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.black),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 1, colors.grey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )

    elements.append(table)

    elements.append(Spacer(1, 25))

    # TOTAL
    elements.append(
        Paragraph(f"<b>Total Amount:</b> ₹{order.total_amount}", styles["Heading2"])
    )

    doc.build(elements)

    return response
