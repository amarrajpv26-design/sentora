from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Q, F
from django.contrib import messages
from orders.models import Order
from products.models import ProductVariant
from django.db import transaction

# ==========================================
# A. ORDER MANAGEMENT WORKFLOWS
# ==========================================


@staff_member_required(login_url="user_login")
def admin_orders_list(request):
    """
    i. List orders in descending order by order date
    iv. Search, sort, and filter with clear functionality
    v. Pagination
    """
    orders = Order.objects.all().order_by("-created_at")

    # iv. Search by OrderID, full_name, or user email
    search_query = request.GET.get("search", "").strip()
    if search_query:
        orders = orders.filter(
            Q(order_id__icontains=search_query)
            | Q(full_name__icontains=search_query)
            | Q(user__email__icontains=search_query)
        )

    # iv. Filter by Status
    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        orders = orders.filter(order_status=status_filter)

    # v. Pagination (12 entries per grid layout view)
    paginator = Paginator(orders, 12)
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
    """ii. Show orderID, date, user details, snapshot variables, and active item details"""
    # Look up using your specific alphanumeric unique string field
    order = get_object_or_404(Order, order_id=order_id)
    items = order.items.all()
    return render(
        request, "management/order_detail.html", {"order": order, "items": items}
    )


@staff_member_required(login_url="user_login")
@transaction.atomic
def change_order_status(request, order_id):

    if request.method == "POST":

        order = get_object_or_404(Order, order_id=order_id)

        new_status = request.POST.get("order_status")
        old_status = order.order_status

        valid_statuses = dict(Order.ORDER_STATUS)

        if new_status not in valid_statuses:
            messages.error(request, "Invalid order status.")
            return redirect("management:admin_orders_list")

        # ==============================
        # CANCEL / RETURN ORDER
        # ==============================

        if (
            new_status in ["CANCELLED", "RETURNED"]
            and old_status not in ["CANCELLED", "RETURNED"]
        ):

            for item in order.items.all():

                # avoid double restock
                if item.item_status == "ACTIVE":

                    if item.product_variant:

                        ProductVariant.objects.filter(
                            id=item.product_variant.id
                        ).update(
                            stock=F("stock") + item.quantity
                        )

                    item.item_status = new_status
                    item.save()

        # ==============================
        # REACTIVATE ORDER
        # ==============================

        elif (
            old_status in ["CANCELLED", "RETURNED"]
            and new_status in ["PENDING", "PROCESSING", "SHIPPED"]
        ):

            for item in order.items.all():

                if item.product_variant:

                    variant = item.product_variant

                    # check inventory before deducting
                    if variant.stock < item.quantity:

                        messages.error(
                            request,
                            f"Not enough stock for {item.product_name}"
                        )

                        return redirect(
                            "management:admin_order_detail",
                            order_id=order.order_id
                        )

            # deduct after validation
            for item in order.items.all():

                ProductVariant.objects.filter(
                    id=item.product_variant.id
                ).update(
                    stock=F("stock") - item.quantity
                )

                item.item_status = "ACTIVE"
                item.save()

        # ==============================
        # SAVE ORDER STATUS
        # ==============================

        order.order_status = new_status
        order.save()

        messages.success(
            request,
            f"Order status updated to {order.get_order_status_display()}."
        )

    return redirect(
        "management:admin_order_detail",
        order_id=order.order_id
    )


# ==========================================
# B. INVENTORY / STOCK MANAGEMENT WORKFLOWS
# ==========================================


@staff_member_required(login_url="user_login")
def admin_inventory_list(request):
    """Lists product variants with search options, sorting, and inline updates"""
    variants = ProductVariant.objects.select_related("product", "product__brand").all()

    # Search by variant identifier name, product title, or brand title
    search_query = request.GET.get("search", "").strip()
    if search_query:
        variants = variants.filter(
            Q(name__icontains=search_query)
            | Q(product__name__icontains=search_query)
            | Q(product__brand__name__icontains=search_query)
        )

    # Filter rules for stock status
    stock_filter = request.GET.get("stock_status", "").strip()

    if stock_filter == "abundant":
        variants = variants.filter(stock__gt=5)

    elif stock_filter == "low":
        variants = variants.filter(stock__lte=5, stock__gt=0)
    
    elif stock_filter == "out":
        variants = variants.filter(stock=0)

    # Order/sorting rules
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
    """
    Safely changes an order item status and auto-adjusts variant inventory
    if the item transitions into a CANCELLED or RETURNED state.
    """
    if request.method == "POST":
        # 1. Look up the specific order line item
        # (Assuming your order item model is named OrderItem)
        from orders.models import OrderItem

        item = get_object_or_404(OrderItem, id=item_id)
        new_status = request.POST.get("item_status")
        old_status = item.item_status

        if new_status != old_status:
            # 2. Check if transitioning TO a restock state (Cancelled/Returned) from an active state
            if new_status in ["CANCELLED", "RETURNED"] and old_status == "ACTIVE":
                if item.product_variant:
                    # Increment stock directly in the database to avoid race conditions
                    ProductVariant.objects.filter(id=item.product_variant.id).update(
                        stock=F("stock") + item.quantity
                    )
                    messages.success(
                        request,
                        f"Restocked {item.quantity} units for variant {item.product_name}.",
                    )

            # 3. Check if reverting BACK from Cancelled/Returned to Active (re-deduct stock)
            elif old_status in ["CANCELLED", "RETURNED"] and new_status == "ACTIVE":
                if item.product_variant:
                    variant = item.product_variant
                    if variant.stock >= item.quantity:
                        ProductVariant.objects.filter(id=variant.id).update(
                            stock=F("stock") - item.quantity
                        )
                    else:
                        messages.error(
                            request,
                            f"Insufficient stock available to re-activate this item.",
                        )
                        return redirect(
                            request.META.get(
                                "HTTP_REFERER", "management:admin_orders_list"
                            )
                        )

            item.item_status = new_status
            item.save()
            messages.success(request, f"Item status updated successfully.")

    return redirect(request.META.get("HTTP_REFERER", "management:admin_orders_list"))
