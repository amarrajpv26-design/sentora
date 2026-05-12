from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import HttpResponse
from .models import Wishlist, WishlistItem  # <--- Add this line!
from products.models import ProductVariant
from .wishlist import WishlistManager
from .cart import Cart, CartItem


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

    if success and request.user.is_authenticated:
        WishlistItem.objects.filter(
            wishlist__user=request.user, variant__product=variant.product
        ).delete()

    if request.headers.get("HX-Request"):
        response = HttpResponse("", status=200)

        response["HX-Trigger"] = "update-cart, wishlistUpdated"
        return response

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    return redirect("cart:cart_detail")


def cart_count_only(request):
    cart = Cart(request)
    return HttpResponse(str(len(cart)))


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


def cart_update(request, variant_id):
    cart = Cart(request)
    variant = get_object_or_404(ProductVariant, id=variant_id)

    action = request.POST.get("action")
    current_qty = cart.get_quantity(variant)

    success = False
    message = ""

    if action == "plus":

        if current_qty < variant.stock:

            success, message = cart.add(
                variant, quantity=current_qty + 1, override_quantity=True
            )

            if success:
                message = "Quantity increased"

        else:
            success = False
            message = f"Only {variant.stock} available now"

    elif action == "minus":

        if current_qty > 1:

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

    if request.headers.get("HX-Request"):
        cart = Cart(request)
        response = render(request, "cart/partials/cart_content.html", {"cart": cart})

        response["HX-Trigger"] = message
        return response

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    return redirect("cart:cart_detail")


@require_POST
def wishlist_toggle(request, variant_id):
    if not request.user.is_authenticated:
        return HttpResponse(status=401)

    variant = get_object_or_404(ProductVariant, id=variant_id)
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)

    item = WishlistItem.objects.filter(wishlist=wishlist, variant=variant).first()

    if item:
        item.delete()
        is_in_wishlist = False
    else:
        WishlistItem.objects.create(wishlist=wishlist, variant=variant)
        is_in_wishlist = True

    response = render(
        request,
        "cart/partials/wishlist_button.html",
        {
            "is_in_wishlist": is_in_wishlist,
            "product": variant.product,
            "variant": variant,
        },
    )

    response["HX-Trigger"] = "wishlistUpdated"

    return response


def wishlist_remove(request, variant_id):
    if not request.user.is_authenticated:
        return HttpResponse(status=401)

    wishlist = Wishlist.objects.filter(user=request.user).first()
    if wishlist:
        WishlistItem.objects.filter(wishlist=wishlist, variant_id=variant_id).delete()

    response = HttpResponse("", status=200)

    response["HX-Trigger"] = "wishlistUpdated"

    return response


def wishlist_count_only(request):

    if not request.user.is_authenticated:
        return HttpResponse("0")

    wishlist = Wishlist.objects.filter(user=request.user).first()
    count = wishlist.items.count() if wishlist else 0

    return HttpResponse(str(count))


def wishlist_detail(request):
    wishlist = Wishlist.objects.filter(user=request.user).first()

    wishlist_items = WishlistItem.objects.filter(wishlist=wishlist).select_related(
        "variant", "variant__product", "variant__product__brand"
    )

    return render(
        request, "cart/wishlist_detail.html", {"wishlist_items": wishlist_items}
    )
