from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import HttpResponse

from products.models import ProductVariant
from .cart import Cart, CartItem


# ----------------------------
# ADD TO CART
# ----------------------------
@require_POST
def cart_add(request, variant_id):
    cart = Cart(request)
    variant = get_object_or_404(ProductVariant, id=variant_id)

    try:
        quantity = int(request.POST.get("quantity", 1))
        if quantity <= 0:
            quantity = 1
    except (ValueError, TypeError):
        quantity = 1

    override = request.POST.get("override", "").lower() == "true"

    success, message = cart.add(
        variant=variant, quantity=quantity, override_quantity=override
    )

    # HTMX
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Trigger"] = "Added to collection"
        return response

    # Normal request
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    return redirect("cart:cart_detail")


# ----------------------------
# REMOVE FROM CART
# ----------------------------
def cart_remove(request, variant_id):
    cart = Cart(request)
    variant = get_object_or_404(ProductVariant, id=variant_id)

    cart.remove(variant)

    message = "Removed from collection"
    success = True

    if request.headers.get("HX-Request"):
        response = render(request, "cart/partials/cart_content.html", {"cart": cart})
        response["HX-Trigger"] = message
        return response

    messages.success(request, message)
    return redirect("cart:cart_detail")


# ----------------------------
# CART DETAIL
# ----------------------------
def cart_detail(request):
    cart = Cart(request)

    available_items = []
    unavailable_items = []

    for item in cart:
        if item["is_available"]:
            available_items.append(item)
        else:
            unavailable_items.append(item)

    return render(
        request,
        "cart/detail.html",
        {
            "available_items": available_items,
            "unavailable_items": unavailable_items,
            "cart": cart,
        },
    )


# ----------------------------
# UPDATE QUANTITY
# ----------------------------
def cart_update(request, variant_id):
    cart = Cart(request)
    variant = get_object_or_404(ProductVariant, id=variant_id)

    action = request.POST.get("action")
    current_qty = cart.get_quantity(variant)

    success = False
    message = ""

    # ---------------- PLUS ----------------
    if action == "plus":

        # ONLY increase if stock allows
        if current_qty < variant.stock:

            success, message = cart.add(
                variant, quantity=current_qty + 1, override_quantity=True
            )

            if success:
                message = "Quantity increased"

        else:
            success = False
            message = f"Only {variant.stock} available now"

    # ---------------- MINUS ----------------
    elif action == "minus":

        if current_qty > 1:

            # ---------------- DB CART ----------------
            if request.user.is_authenticated:

                item = CartItem.objects.filter(
                    cart=cart.cart_obj, variant=variant
                ).first()

                if item:
                    item.quantity -= 1
                    if item.quantity <= 0:
                        item.delete()
                    else:
                        item.save()

            # ---------------- SESSION CART ----------------
            else:

                variant_id = str(variant.id)

                if variant_id in cart.cart:
                    cart.cart[variant_id]["quantity"] -= 1
                    cart.save()

            success = True
            message = "Quantity decreased"

        else:
            cart.remove(variant)
            success = True
            message = "Item removed from cart"

    else:
        success = False
        message = "Invalid action"

    # ---------------- HTMX ----------------
    if request.headers.get("HX-Request"):
        cart = Cart(request)
        response = render(request, "cart/partials/cart_content.html", {"cart": cart})

        response["HX-Trigger"] = message
        return response

    # ---------------- NORMAL ----------------
    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    return redirect("cart:cart_detail")
