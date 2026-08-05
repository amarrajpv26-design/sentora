from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.contrib import messages
from django.http import HttpResponse
from django.urls import reverse
from .models import Wishlist, WishlistItem  # <--- Add this line!
from products.models import ProductVariant
from .wishlist import WishlistManager
import json
from .cart import Cart, CartItem
from django.contrib.auth.decorators import login_required
from offers.utils import get_effective_price
from django.utils.http import url_has_allowed_host_and_scheme, urlencode



@require_POST
def cart_add(request, variant_id):
    if not request.user.is_authenticated:
        if request.headers.get("HX-Request"):
            response = HttpResponse(status=401)
            response["HX-Trigger"] = json.dumps(
                {"showMessage": "Please log in to add items to your cart"}
            )
            return response
        messages.error(request, "Please log in to add items to your cart.")
        login_url = reverse("user_login")
        referer = request.META.get("HTTP_REFERER", "/")
        if url_has_allowed_host_and_scheme(
            url=referer,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            next_url = referer
        else:
            next_url = "/"
        return redirect(f"{login_url}?{urlencode({'next': next_url})}")

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
            wishlist__user=request.user, variant=variant
        ).delete()

    if request.headers.get("HX-Request"):
        response = HttpResponse("", status=200)
        if success:
            response["HX-Trigger"] = json.dumps({"showMessage": "Item added to cart"})
            response["HX-Trigger-After-Swap"] = "cartUpdated, wishlistUpdated"
        else:
            response["HX-Trigger"] = json.dumps({"showMessage": message})

        return response

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    referer = request.META.get("HTTP_REFERER", "")
    if url_has_allowed_host_and_scheme(
        url=referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(referer)
    return redirect("shop:product_list")


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
    if not request.user.is_authenticated:
        return HttpResponse(status=401)

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
            message = "Item Removed from the cart"

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
        response = HttpResponse(status=401)
        response["HX-Trigger"] = json.dumps(
            {"showMessage": "Please log in to save items to your wishlist"}
        )
        return response

    variant = get_object_or_404(ProductVariant, id=variant_id)
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)

    # IMPORTANT: match on the exact variant only. Matching on
    # variant__product here would wipe out every other size of the
    # same product from the wishlist whenever any one size is toggled.
    existing_item = WishlistItem.objects.filter(
        wishlist=wishlist, variant=variant
    ).first()

    if existing_item:
        existing_item.delete()
        is_in_wishlist = False
        message = "Item removed from wishlist"
    else:
        WishlistItem.objects.create(wishlist=wishlist, variant=variant)
        is_in_wishlist = True
        message = "Item added to wishlist"

    response = render(
        request,
        "cart/partials/wishlist_button_wrapper.html",
        {
            "is_in_wishlist": is_in_wishlist,
            "product": variant.product,
            "variant": variant,
        },
    )

    response["HX-Trigger"] = json.dumps({"showMessage": message})
    response["HX-Trigger-After-Swap"] = "wishlistUpdated"

    return response


def wishlist_remove(request, variant_id):
    if not request.user.is_authenticated:
        return HttpResponse(status=401)

    wishlist = Wishlist.objects.filter(user=request.user).first()
    if wishlist:
        WishlistItem.objects.filter(wishlist=wishlist, variant_id=variant_id).delete()

    response = HttpResponse("", status=200)

    response["HX-Trigger"] = json.dumps({"showMessage": "Item removed from wishlist"})
    response["HX-Trigger-After-Swap"] = "wishlistUpdated"

    return response


def wishlist_count_only(request):

    if not request.user.is_authenticated:
        return HttpResponse("0")

    wishlist = Wishlist.objects.filter(user=request.user).first()
    count = wishlist.items.count() if wishlist else 0

    return HttpResponse(str(count))


@login_required(login_url="user_login")
def wishlist_detail(request):
    wishlist = Wishlist.objects.filter(user=request.user).first()

    wishlist_items = WishlistItem.objects.filter(wishlist=wishlist).select_related(
        "variant", "variant__product", "variant__product__brand"
    )
    for item in wishlist_items:
        effective_price, offer_label = get_effective_price(item.variant)
        item.variant.effective_price = effective_price
        item.variant.offer_label = offer_label

    return render(
        request, "cart/wishlist_detail.html", {"wishlist_items": wishlist_items}
    )


def wishlist_button_partial(request, variant_id):
    variant = get_object_or_404(ProductVariant, id=variant_id)

    is_in_wishlist = False

    if request.user.is_authenticated:
        is_in_wishlist = WishlistItem.objects.filter(
            wishlist__user=request.user, variant=variant
        ).exists()

    return render(
        request,
        "cart/partials/wishlist_button_wrapper.html",
        {
            "variant": variant,
            "product": variant.product,
            "is_in_wishlist": is_in_wishlist,
        },
    )