from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from users.models import Address
from cart.cart import Cart
from products.models import ProductVariant

from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction

from orders.models import Order, OrderItem


@login_required
def checkout_view(request):

    cart = Cart(request)

    if len(cart) == 0:

        messages.error(request, "Your cart is empty.")

        return redirect("cart")

    checkout_items = []

    subtotal = 0

    for item in cart:

        variant = item["variant"]
        quantity = item["quantity"]

        if quantity <= 0:
            continue

        if variant.stock < quantity:

            messages.error(request, f"{variant} is out of stock.")

            return redirect("cart")

        mrp_total = variant.price * quantity
        selling_price = variant.offer_price if variant.offer_price else variant.price
        selling_total = selling_price * quantity

        subtotal += selling_total

        checkout_items.append(
            {
                "variant": variant,
                "quantity": quantity,
                "mrp_total": mrp_total,
                "selling_total": selling_total,
                "discount": mrp_total - selling_total,
            }
        )

    addresses = Address.objects.filter(user=request.user).order_by(
        "-is_default", "-created_at"
    )

    # FIX 1: compute total MRP and total discount across all items
    total_mrp = sum(item["mrp_total"] for item in checkout_items)
    total_discount = sum(item["discount"] for item in checkout_items)

    shipping = 0

    final_total = subtotal + shipping
    next_url = request.GET.get("next", "/")
    context = {
        "checkout_type": "cart",
        "checkout_items": checkout_items,
        "addresses": addresses,
        "subtotal": subtotal,
        "discount": total_discount,      # FIX 1
        "mrp_total": total_mrp,          # FIX 1
        "shipping": shipping,
        "final_total": final_total,
        "next_url": next_url,
    }

    return render(request, "checkout/checkout.html", context)


@login_required
def buy_now_checkout_view(request, variant_id):

    variant = get_object_or_404(ProductVariant, id=variant_id)

    quantity = int(request.GET.get("quantity", 1))

    if quantity <= 0:

        messages.error(request, "Invalid quantity.")

        return redirect("product_detail", variant.product.id)

    if variant.stock < quantity:

        messages.error(request, "Product is out of stock.")

        return redirect("product_detail", variant.product.id)

    
    mrp_total = variant.price * quantity
    selling_total = (variant.offer_price or variant.price) * quantity

    checkout_items = [
        {
            "variant": variant,
            "quantity": quantity,
            "selling_total": selling_total,
            "mrp_total": mrp_total,
        }
    ]

    addresses = Address.objects.filter(user=request.user).order_by(
        "-is_default", "-created_at"
    )

    subtotal = selling_total
    discount = mrp_total - selling_total  # FIX 2: was hardcoded 0
    shipping = 0

    final_total = subtotal + shipping

    context = {
        "checkout_type": "buy_now",
        "checkout_items": checkout_items,
        "addresses": addresses,
        "subtotal": subtotal,
        "mrp_total": mrp_total,
        "discount": discount,            # FIX 2
        "shipping": shipping,
        "final_total": final_total,
    }

    return render(request, "checkout/checkout.html", context)


def generate_order_id():

    import uuid

    return f"ORD-{uuid.uuid4().hex[:10].upper()}"


@login_required
@transaction.atomic
def place_order_view(request):

    if request.method != "POST":
        return redirect("checkout")

    checkout_type = request.POST.get("checkout_type")

    selected_address_id = request.POST.get("selected_address")

    if not selected_address_id:

        messages.error(request, "Please select an address.")

        return redirect("checkout")

    address = get_object_or_404(Address, id=selected_address_id, user=request.user)

    checkout_items = []

    subtotal = 0

    # CART CHECKOUT
    if checkout_type == "cart":

        cart = Cart(request)

        if len(cart) == 0:

            messages.error(request, "Your cart is empty.")

            return redirect("cart")

        for item in cart:

            variant = item["variant"]
            quantity = item["quantity"]

            if variant.stock < quantity:

                messages.error(request, f"{variant} is out of stock.")

                return redirect("checkout")

            mrp_total = variant.price * quantity
            selling_price = (
                variant.offer_price if variant.offer_price else variant.price
            )
            selling_total = selling_price * quantity

            subtotal += selling_total

            checkout_items.append(
                {
                    "variant": variant,
                    "quantity": quantity,
                    "mrp_total": mrp_total,
                    "selling_total": selling_total,
                }
            )

        # FIX 3: define discount for cart (was undefined, would crash)
        discount = sum(
            item["mrp_total"] - item["selling_total"] for item in checkout_items
        )

    # BUY NOW CHECKOUT
    elif checkout_type == "buy_now":

        variant_id = request.POST.get("variant_id")

        quantity = int(request.POST.get("quantity", 1))

        variant = get_object_or_404(ProductVariant, id=variant_id)

        if variant.stock < quantity:

            messages.error(request, "Product is out of stock.")

            return redirect("checkout")

        mrp_total = variant.price * quantity
        selling_total = (variant.offer_price or variant.price) * quantity

        subtotal = selling_total
        discount = mrp_total - selling_total
        checkout_items = [
            {
                "variant": variant,
                "quantity": quantity,
                "mrp_total": mrp_total,
                "discount": discount,
                "selling_total": selling_total,
            }
        ]

    else:

        return redirect("checkout")

    shipping = 0

    final_total = subtotal + shipping

    # CREATE ORDER
    order = Order.objects.create(
        user=request.user,
        order_id=generate_order_id(),
        address=address,
        full_name=address.full_name,
        phone_number=address.phone_number,
        address_line_1=address.address_line_1,
        address_line_2=address.address_line_2,
        city=address.city,
        state=address.state,
        pincode=address.pincode,
        subtotal=subtotal,
        discount=discount,
        shipping_charge=shipping,
        total_amount=final_total,
        payment_method="COD",
        payment_status="PENDING",
        order_status="PENDING",
    )

    # CREATE ORDER ITEMS
    for item in checkout_items:

        variant = item["variant"]
        quantity = item["quantity"]
        item_subtotal = item["selling_total"]

        OrderItem.objects.create(
            order=order,
            product_variant=variant,
            product_name=str(variant),
            quantity=quantity,
            price=variant.price,
            subtotal=item_subtotal,
        )

        # REDUCE STOCK
        variant.stock -= quantity
        variant.save()

    # CLEAR CART
    if checkout_type == "cart":

        cart.clear()

    return redirect("order_success", order_id=order.order_id)


@login_required
def order_success_view(request, order_id):

    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    context = {
        "order": order,
        "order_id": order.order_id,
    }

    return render(request, "checkout/success.html", context)