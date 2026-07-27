from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from users.models import Address
from cart.cart import Cart
from products.models import ProductVariant
from django.db.models import F, Q
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from cart.models import WishlistItem
from orders.models import Order, OrderItem
from coupons.models import Coupon, CouponUsage
import razorpay
from wallets.models import WalletTransaction
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.http import JsonResponse
from decimal import Decimal
from offers.utils import get_effective_price
from offers.utils import handle_order_referral_events


def get_applied_coupon_discount(request, subtotal):

    coupon_id = request.session.get("coupon_id")

    if not coupon_id:
        return None, Decimal("0.00")

    try:
        coupon = Coupon.objects.get(id=coupon_id)
    except Coupon.DoesNotExist:
        del request.session["coupon_id"]
        return None, Decimal("0.00")

    is_valid, error_message = coupon.is_valid_for_user(request.user, subtotal)

    if not is_valid:
        del request.session["coupon_id"]
        messages.warning(
            request, f"Coupon '{coupon.code}' was removed: {error_message}"
        )
        return None, Decimal("0.00")

    discount_amount = coupon.calculate_discount(subtotal)
    return coupon, discount_amount


def record_coupon_usage(order):

    if not order.applied_coupon:
        return

    CouponUsage.objects.create(
        coupon=order.applied_coupon,
        user=order.user,
        order=order,
        discount_amount=order.coupon_discount,
    )
    Coupon.objects.filter(pk=order.applied_coupon.pk).update(
        used_count=F("used_count") + 1
    )


def decrement_stock_or_fail(variant_id, quantity):
    """
    Atomically decrement stock only if enough is available *right now*.

    This is a single conditional UPDATE (UPDATE ... SET stock = stock - qty
    WHERE id = ? AND stock >= qty). Because the check and the decrement are
    the same database statement, there is no window between "check stock"
    and "reduce stock" where another concurrent request could sneak in and
    oversell the last few units. This replaces the old pattern of doing a
    separate select_for_update() check and then, much later, an unguarded
    F('stock') - quantity update.

    Returns True if the row was updated (i.e. stock was sufficient and has
    now been reduced), False if there wasn't enough stock (nothing was
    changed).
    """
    updated = ProductVariant.objects.filter(
        pk=variant_id, stock__gte=quantity
    ).update(stock=F("stock") - quantity)
    return updated == 1


@login_required
def checkout_view(request):
    context = {}

    cart = Cart(request)

    if len(cart) == 0:
        messages.error(request, "Your cart is empty.")
        return redirect("cart:cart_detail")

    checkout_items = []
    subtotal = 0

    for item in cart:

        variant = item["variant"]
        quantity = item["quantity"]

        if quantity <= 0:
            continue

        if variant.stock < quantity:
            messages.error(request, f"{variant} is out of stock.")
            return redirect("cart:cart_detail")

        mrp_total = variant.price * quantity
        selling_price, offer_label = get_effective_price(variant)
        selling_total = selling_price * quantity

        subtotal += selling_total

        checkout_items.append(
            {
                "variant": variant,
                "quantity": quantity,
                "mrp_total": mrp_total,
                "selling_total": selling_total,
                "discount": mrp_total - selling_total,
                "unit_price": selling_price,
                "offer_label": offer_label,
            }
        )

    addresses = Address.objects.filter(user=request.user).order_by(
        "-is_default", "-created_at"
    )

    total_mrp = sum(item["mrp_total"] for item in checkout_items)
    total_discount = sum(item["discount"] for item in checkout_items)

    shipping = 0

    # ---------------- Coupon Logic ----------------
    applied_coupon, coupon_discount_amount = get_applied_coupon_discount(
        request, subtotal
    )
    # ------------------------------------------------

    final_total = (subtotal + shipping) - coupon_discount_amount

    # ---------------- Wallet Info ----------------
    wallet_balance = Decimal("0.00")
    wallet_sufficient = False
    wallet_shortfall = Decimal("0.00")

    if hasattr(request.user, "wallet"):
        wallet_balance = request.user.wallet.balance
        wallet_sufficient = wallet_balance >= final_total

        if not wallet_sufficient:
            wallet_shortfall = final_total - wallet_balance

    context["wallet_balance"] = wallet_balance
    # ---------------------------------------------

    next_url = request.GET.get("next", "/")

    context = {
        "checkout_type": "cart",
        "checkout_items": checkout_items,
        "addresses": addresses,
        "subtotal": subtotal,
        "discount": total_discount,
        "mrp_total": total_mrp,
        "shipping": shipping,
        "final_total": final_total,
        "next_url": next_url,
        "coupon": applied_coupon,
        "coupon_discount": coupon_discount_amount,
        "wallet_balance": wallet_balance,
        "wallet_sufficient": wallet_sufficient,
        "wallet_shortfall": wallet_shortfall,
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
    selling_price, offer_label = get_effective_price(variant)
    selling_total = selling_price * quantity

    checkout_items = [
        {
            "variant": variant,
            "quantity": quantity,
            "selling_total": selling_total,
            "mrp_total": mrp_total,
            "unit_price": selling_price,
            "offer_label": offer_label,
        }
    ]

    addresses = Address.objects.filter(user=request.user).order_by(
        "-is_default", "-created_at"
    )

    subtotal = selling_total
    discount = mrp_total - selling_total
    shipping = 0

    # ---------------- Coupon Logic ----------------
    applied_coupon, coupon_discount_amount = get_applied_coupon_discount(
        request, subtotal
    )
    # ------------------------------------------------

    final_total = (subtotal + shipping) - coupon_discount_amount

    wallet_balance = Decimal("0.00")
    wallet_sufficient = False
    wallet_shortfall = Decimal("0.00")

    if hasattr(request.user, "wallet"):
        wallet_balance = request.user.wallet.balance
        wallet_sufficient = wallet_balance >= final_total

        if not wallet_sufficient:
            wallet_shortfall = final_total - wallet_balance

    context = {
        "checkout_type": "buy_now",
        "checkout_items": checkout_items,
        "addresses": addresses,
        "subtotal": subtotal,
        "mrp_total": mrp_total,
        "discount": discount,
        "shipping": shipping,
        "final_total": final_total,
        "coupon": applied_coupon,
        "coupon_discount": coupon_discount_amount,
        "wallet_balance": wallet_balance,
        "wallet_sufficient": wallet_sufficient,
        "wallet_shortfall": wallet_shortfall,
    }

    return render(request, "checkout/checkout.html", context)


def generate_order_id():
    import uuid
    return f"ORD-{uuid.uuid4().hex[:10].upper()}"


@login_required
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

    if checkout_type == "cart":

        cart = Cart(request)

        if len(cart) == 0:
            messages.error(request, "Your cart is empty.")
            return redirect("cart")

        with transaction.atomic():
            for item in cart:

                variant = item["variant"]
                quantity = item["quantity"]

                variant = ProductVariant.objects.select_for_update().get(pk=variant.pk)

                if variant.stock < quantity:
                    messages.error(request, f"{variant} is out of stock.")
                    return redirect("checkout")

                mrp_total = variant.price * quantity
                selling_price, _ = get_effective_price(variant)
                selling_total = selling_price * quantity
                subtotal += selling_total

                checkout_items.append(
                    {
                        "variant": variant,
                        "quantity": quantity,
                        "mrp_total": mrp_total,
                        "selling_total": selling_total,
                        "unit_price": selling_price,
                    }
                )

        discount = sum(
            item["mrp_total"] - item["selling_total"] for item in checkout_items
        )

    elif checkout_type == "buy_now":

        variant_id = request.POST.get("variant_id")
        quantity = int(request.POST.get("quantity", 1))

        with transaction.atomic():
            variant = ProductVariant.objects.select_for_update().get(pk=variant_id)

            if variant.stock < quantity:
                messages.error(request, "Product is out of stock.")
                return redirect("checkout")

        mrp_total = variant.price * quantity
        selling_price, _ = get_effective_price(variant)
        selling_total = selling_price * quantity
        subtotal = selling_total
        discount = mrp_total - selling_total

        checkout_items = [
            {
                "variant": variant,
                "quantity": quantity,
                "mrp_total": mrp_total,
                "discount": discount,
                "selling_total": selling_total,
                "unit_price": selling_price,
            }
        ]

    else:
        return redirect("checkout")

    shipping = 0

    # ---------------- Coupon Logic ----------------
    applied_coupon, coupon_discount_amount = get_applied_coupon_discount(
        request, subtotal
    )
    # ------------------------------------------------

    final_total = (subtotal + shipping) - coupon_discount_amount

    payment_method = request.POST.get("payment_method", "COD")

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
        applied_coupon=applied_coupon,
        coupon_discount=coupon_discount_amount,
        payment_method=payment_method,
        payment_status="PENDING",
        order_status="PENDING",
    )

    for item in checkout_items:
        variant = item["variant"]
        quantity = item["quantity"]
        item_subtotal = item["selling_total"]
        unit_price = item["unit_price"]

        OrderItem.objects.create(
            order=order,
            product_variant=variant,
            product_name=str(variant),
            quantity=quantity,
            price=unit_price,
            subtotal=item_subtotal,
        )

    # =====================================================
    # ONLINE PAYMENT (RAZORPAY)
    # =====================================================
    if payment_method == "ONLINE":
        # NOTE: stock is intentionally NOT decremented here. For online
        # payments, stock is only reduced once payment is verified in
        # payment_verify_view, using the same decrement_stock_or_fail()
        # helper used below for COD/WALLET.

        client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )

        razorpay_amount = int(order.total_amount * 100)

        razorpay_order_data = {
            "amount": razorpay_amount,
            "currency": "INR",
            "receipt": order.order_id,
            "payment_capture": 1,
        }

        try:
            razorpay_order = client.order.create(data=razorpay_order_data)
        except Exception:
            order.delete()
            messages.error(request, "Payment gateway unavailable. Please try again.")
            return redirect("checkout")

        order.razorpay_order_id = razorpay_order["id"]
        order.save()

        addresses = Address.objects.filter(user=request.user).order_by(
            "-is_default", "-created_at"
        )

        context = {
            "order": order,
            "razorpay_order_id": razorpay_order["id"],
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "razorpay_amount": razorpay_amount,
            "final_total": order.total_amount,
            "addresses": addresses,
            "checkout_items": checkout_items,
            "subtotal": subtotal,
            "discount": discount,
            "shipping": shipping,
            "trigger_payment": True,
        }

        return render(request, "checkout/checkout.html", context)

    # =====================================================
    # WALLET PAYMENT
    # =====================================================
    elif payment_method == "WALLET":
        try:
            user_wallet = request.user.wallet
        except Exception:
            order.delete()
            messages.error(request, "Wallet not found.")
            return redirect("checkout")

        if user_wallet.balance < order.total_amount:
            order.delete()
            messages.error(
                request,
                "Insufficient wallet balance. Please choose another payment method.",
            )
            return redirect("checkout")

        # ---- Atomic stock reservation before touching the wallet ----
        # We check-and-decrement stock for every item first. If any item
        # sold out between page-load and this exact moment, we roll back
        # the whole order and refund nothing (since nothing was ever
        # debited yet at this point).
        with transaction.atomic():
            for item in checkout_items:
                variant = item["variant"]
                quantity = item["quantity"]

                if not decrement_stock_or_fail(variant.pk, quantity):
                    transaction.set_rollback(True)
                    order.delete()
                    messages.error(
                        request,
                        f"Sorry, {variant} just went out of stock. "
                        f"Please review your order and try again.",
                    )
                    return redirect("checkout")

        user_wallet.balance -= order.total_amount
        user_wallet.save()

        WalletTransaction.objects.create(
            wallet=user_wallet,
            amount=order.total_amount,
            transaction_type="DEBIT",
            purpose="PURCHASE",
            order_id=order.order_id,
            description=f"Wallet debit payment for Order #{order.order_id}",
        )

        order.payment_status = "PAID"
        order.order_status = "CONFIRMED"
        order.save()

        ordered_variants = [item["variant"] for item in checkout_items]

        WishlistItem.objects.filter(
            wishlist__user=request.user,
            variant__in=ordered_variants,
        ).delete()

        if checkout_type == "buy_now":
            variant = checkout_items[0]["variant"]
            ordered_qty = checkout_items[0]["quantity"]

            from cart.models import CartItem

            cart_item = CartItem.objects.filter(
                cart__user=request.user,
                variant=variant,
            ).first()

            if cart_item:
                if cart_item.quantity <= ordered_qty:
                    cart_item.delete()
                else:
                    cart_item.quantity -= ordered_qty
                    cart_item.save()

        if checkout_type == "cart":
            cart.clear()

        record_coupon_usage(order)
        if "coupon_id" in request.session:
            del request.session["coupon_id"]

        handle_order_referral_events(order)

        # ── SUCCESS MESSAGE ──
        messages.success(
            request,
            f"₹{order.total_amount} paid successfully via Wallet!"
        )
        return redirect("order_success", order_id=order.order_id)

    # =====================================================
    # COD
    # =====================================================
    else:

        # ---- Atomic stock reservation ----
        # Check-and-decrement stock for every item in one atomic block.
        # If any item sold out between page-load and this exact moment,
        # roll back and cancel the order instead of allowing negative
        # stock or an oversold item.
        with transaction.atomic():
            for item in checkout_items:
                variant = item["variant"]
                quantity = item["quantity"]

                if not decrement_stock_or_fail(variant.pk, quantity):
                    transaction.set_rollback(True)
                    order.delete()
                    messages.error(
                        request,
                        f"Sorry, {variant} just went out of stock. "
                        f"Please review your order and try again.",
                    )
                    return redirect("checkout")

        ordered_variants = [item["variant"] for item in checkout_items]

        WishlistItem.objects.filter(
            wishlist__user=request.user,
            variant__in=ordered_variants,
        ).delete()

        if checkout_type == "buy_now":
            variant = checkout_items[0]["variant"]
            ordered_qty = checkout_items[0]["quantity"]

            from cart.models import CartItem

            cart_item = CartItem.objects.filter(
                cart__user=request.user,
                variant=variant,
            ).first()

            if cart_item:
                if cart_item.quantity <= ordered_qty:
                    cart_item.delete()
                else:
                    cart_item.quantity -= ordered_qty
                    cart_item.save()

        if checkout_type == "cart":
            cart.clear()

        record_coupon_usage(order)
        if "coupon_id" in request.session:
            del request.session["coupon_id"]

        handle_order_referral_events(order)

        # ── SUCCESS MESSAGE ──
        messages.success(
            request,
            f"Order placed successfully! ₹{order.total_amount} to be paid on delivery."
        )
        return redirect("order_success", order_id=order.order_id)


@csrf_exempt
def payment_verify_view(request):

    order_id = request.GET.get("order_id")

    if request.method == "POST":
        razorpay_payment_id = request.POST.get("razorpay_payment_id")
        razorpay_signature = request.POST.get("razorpay_signature")
    else:
        razorpay_payment_id = request.GET.get("razorpay_payment_id")
        razorpay_signature = request.GET.get("razorpay_signature")

    order = get_object_or_404(Order, order_id=order_id)

    # ---- Idempotency guard ----
    # This view can be hit more than once for the same order: Razorpay's
    # in-modal handler submits the hidden form AND, separately, the bank
    # redirect flow can POST back to callback_url, and users can also hit
    # back/refresh. Without this guard, stock would be decremented twice,
    # coupon usage recorded twice, and duplicate CouponUsage rows created
    # for a single real payment.
    if order.payment_status == "PAID":
        return redirect("order_success", order_id=order.order_id)

    # ── Handle bank decline posted by Razorpay via callback_url ──
    if request.method == "POST" and request.POST.get("error[code]"):
        order.payment_status = "FAILED"
        order.order_status = "PENDING"
        order.save()
        messages.error(request, "Payment was declined by the bank. Please try again.")
        return redirect(f"/checkout/payment/failed/?order_id={order.order_id}")

    client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )

    params_dict = {
        "razorpay_order_id": order.razorpay_order_id,
        "razorpay_payment_id": razorpay_payment_id,
        "razorpay_signature": razorpay_signature,
    }

    try:
        client.utility.verify_payment_signature(params_dict)

        order.payment_status = "PAID"
        order.order_status = "CONFIRMED"
        order.razorpay_payment_id = razorpay_payment_id
        order.razorpay_signature = razorpay_signature
        order.save()

        # ---- Atomic stock decrement, now that money is actually captured ----
        # Payment is already captured by Razorpay at this point, so we can
        # no longer "cancel" the order the way COD/WALLET can if stock ran
        # out. Instead, any item that can't be fulfilled gets flagged for
        # manual handling (refund/backorder) rather than silently going
        # negative in stock.
        oversold_items = []

        with transaction.atomic():
            for item in order.items.all():
                if item.product_variant:
                    ok = decrement_stock_or_fail(
                        item.product_variant.pk, item.quantity
                    )
                    if not ok:
                        oversold_items.append(item)

        if oversold_items:
            order.order_status = "BACKORDERED"
            order.save(update_fields=["order_status"])
            messages.warning(
                request,
                "Your payment was successful, but one or more items just "
                "sold out. Our team will contact you about a refund or "
                "restock for the affected item(s).",
            )

        from cart.models import CartItem
        CartItem.objects.filter(cart__user=order.user).delete()

        ordered_variants = [
            item.product_variant for item in order.items.all() if item.product_variant
        ]
        WishlistItem.objects.filter(
            wishlist__user=order.user, variant__in=ordered_variants
        ).delete()

        record_coupon_usage(order)

        if "coupon_id" in request.session:
            del request.session["coupon_id"]

        handle_order_referral_events(order)

        from django.contrib.auth import login as auth_login
        if not request.user.is_authenticated:
            auth_login(
                request,
                order.user,
                backend="django.contrib.auth.backends.ModelBackend",
            )

        # ── SUCCESS MESSAGE ──
        messages.success(
            request,
            f"₹{order.total_amount} paid successfully via Online Payment!"
        )
        return redirect("order_success", order_id=order.order_id)

    except Exception as e:
        print("RAZORPAY VERIFY ERROR:", str(e))

        order.payment_status = "FAILED"
        order.order_status = "PENDING"
        order.save()
        messages.error(request, "Payment signature verification failed.")
        return redirect(f"/checkout/payment/failed/?order_id={order.order_id}")


def payment_failed_view(request):
    order_id = request.GET.get("order_id")
    order = get_object_or_404(Order, order_id=order_id)

    if order.payment_status != "PAID":
        order.payment_status = "FAILED"
        order.save()

    context = {
        "order": order,
        "order_id": order.order_id,
        "final_total": order.total_amount,
    }
    return render(request, "checkout/failure.html", context)


def order_success_view(request, order_id):
    order = get_object_or_404(Order, order_id=order_id)
    return render(
        request, "checkout/success.html", {"order_id": order.order_id, "order": order}
    )


@login_required
def retry_payment_view(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)

    if order.payment_status == "PAID":
        messages.info(request, "This order is already paid.")
        return redirect("order_success", order_id=order.order_id)

    if order.order_status not in ["PENDING", "CONFIRMED", "SHIPPED", "OUT_FOR_DELIVERY"]:
        messages.error(request, "This order is not eligible for payment.")
        return redirect("order_detail", order_id=order.order_id)

    # ── Wallet info for the template ──
    wallet_balance = Decimal("0.00")
    wallet_sufficient = False
    wallet_shortfall = Decimal("0.00")

    if hasattr(request.user, "wallet"):
        wallet_balance = request.user.wallet.balance
        wallet_sufficient = wallet_balance >= order.total_amount
        if not wallet_sufficient:
            wallet_shortfall = order.total_amount - wallet_balance

    # ── GET: show payment method selection page ──
    if request.method == "GET":
        context = {
            "order": order,
            "final_total": order.total_amount,
            "wallet_balance": wallet_balance,
            "wallet_sufficient": wallet_sufficient,
            "wallet_shortfall": wallet_shortfall,
        }
        return render(request, "checkout/retry_payment.html", context)

    # ── POST: process the chosen payment method ──
    payment_method = request.POST.get("payment_method", "ONLINE")

    # ── WALLET ──
    if payment_method == "WALLET":
        try:
            user_wallet = request.user.wallet
        except Exception:
            messages.error(request, "Wallet not found.")
            return redirect("retry_payment", order_id=order.order_id)

        if user_wallet.balance < order.total_amount:
            messages.error(request, "Insufficient wallet balance.")
            return redirect("retry_payment", order_id=order.order_id)

        # ---- Atomic stock reservation for the retry-payment path ----
        # This order's items were never stocked-out at creation time (COD
        # orders don't decrement stock until paid), so we check-and-decrement
        # here, same as the main WALLET flow above.
        active_items = list(order.items.filter(item_status="ACTIVE"))

        with transaction.atomic():
            for item in active_items:
                if item.product_variant:
                    if not decrement_stock_or_fail(
                        item.product_variant.pk, item.quantity
                    ):
                        transaction.set_rollback(True)
                        messages.error(
                            request,
                            f"Sorry, {item.product_variant} just went out of "
                            f"stock. Please contact support about this order.",
                        )
                        return redirect("retry_payment", order_id=order.order_id)

        user_wallet.balance -= order.total_amount
        user_wallet.save()

        WalletTransaction.objects.create(
            wallet=user_wallet,
            amount=order.total_amount,
            transaction_type="DEBIT",
            purpose="PURCHASE",
            order_id=order.order_id,
            description=f"Wallet payment for Order #{order.order_id}",
        )

        order.payment_method = "WALLET"
        order.payment_status = "PAID"
        order.order_status = "CONFIRMED"
        order.save()

        # ── SUCCESS MESSAGE ──
        messages.success(
            request,
            f"₹{order.total_amount} paid successfully via Wallet!"
        )
        return redirect("order_success", order_id=order.order_id)

    # ── COD ──
    # COD stays PENDING — no payment yet, just method preference recorded
    if payment_method == "COD":
        order.payment_method = "COD"
        order.payment_status = "PENDING"
        order.order_status = "PENDING"
        order.save()

        # ── SUCCESS MESSAGE ──
        messages.success(
            request,
            f"Order updated to Cash on Delivery. ₹{order.total_amount} to be paid on delivery."
        )
        return redirect("order_success", order_id=order.order_id)

    # ── ONLINE (Razorpay) ──
    client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )
    razorpay_amount = int(order.total_amount * 100)

    try:
        razorpay_order = client.order.create(data={
            "amount": razorpay_amount,
            "currency": "INR",
            "receipt": order.order_id,
            "payment_capture": 1,
        })
    except Exception:
        messages.error(request, "Payment gateway unavailable. Please try again.")
        return redirect("retry_payment", order_id=order.order_id)

    order.payment_method = "ONLINE"
    order.razorpay_order_id = razorpay_order["id"]
    order.save()

    context = {
        "order": order,
        "razorpay_order_id": razorpay_order["id"],
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "razorpay_amount": razorpay_amount,
        "final_total": order.total_amount,
        "wallet_balance": wallet_balance,
        "wallet_sufficient": wallet_sufficient,
        "wallet_shortfall": wallet_shortfall,
        "trigger_payment": True,
    }
    return render(request, "checkout/retry_payment.html", context)


@login_required
def apply_coupon_view(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method."})

    code = request.POST.get("coupon_code", "").strip()

    try:
        subtotal = Decimal(request.POST.get("subtotal", "0") or "0")
    except Exception:
        return JsonResponse({"success": False, "message": "Invalid cart total."})

    if "coupon_id" in request.session:
        return JsonResponse(
            {
                "success": False,
                "message": "A coupon is already applied. Remove it first to use a different one.",
            }
        )

    if not code:
        return JsonResponse({"success": False, "message": "Please enter a coupon code."})

    try:
        coupon = Coupon.objects.get(code__iexact=code, active=True)
    except Coupon.DoesNotExist:
        return JsonResponse({"success": False, "message": "Invalid coupon code."})

    is_valid, error_message = coupon.is_valid_for_user(request.user, subtotal)
    if not is_valid:
        return JsonResponse({"success": False, "message": error_message})

    request.session["coupon_id"] = coupon.id

    discount_amount = coupon.calculate_discount(subtotal)

    return JsonResponse(
        {
            "success": True,
            "message": f"Coupon '{coupon.code}' applied successfully!",
            "discount": float(discount_amount),
            "code": coupon.code,
        }
    )


@login_required
def remove_coupon_view(request):
    if "coupon_id" in request.session:
        del request.session["coupon_id"]
        return JsonResponse(
            {"success": True, "message": "Coupon removed successfully."}
        )

    return JsonResponse(
        {"success": False, "message": "No active coupon found to remove."}
    )


@login_required
def get_available_coupons(request):
    """
    Returns a JSON list of currently active, non-exhausted coupons,
    annotated with eligibility for the given subtotal and for the
    logged-in user's per-user usage limit. Used by the 'View Available
    Coupons' modal on the checkout page.
    """
    try:
        subtotal = Decimal(request.GET.get("subtotal", "0") or "0")
    except Exception:
        subtotal = Decimal("0.00")

    now = timezone.now()

    coupons = (
        Coupon.objects.filter(active=True, valid_from__lte=now, valid_to__gte=now)
        .filter(Q(usage_limit=0) | Q(used_count__lt=F("usage_limit")))
        .order_by("-created_at")
    )

    has_applied_coupon = "coupon_id" in request.session

    data = []
    for coupon in coupons:

        if coupon.usage_limit_per_user:
            user_uses = CouponUsage.objects.filter(
                coupon=coupon, user=request.user
            ).count()
            if user_uses >= coupon.usage_limit_per_user:
                continue

        eligible = subtotal >= coupon.min_purchase

        if coupon.is_fixed:
            discount_label = f"₹{coupon.discount} OFF"
        else:
            discount_label = f"{coupon.discount}% OFF"
            if coupon.max_discount_amount:
                discount_label += f" up to ₹{coupon.max_discount_amount}"

        data.append(
            {
                "code": coupon.code,
                "description": coupon.description,
                "discount_label": discount_label,
                "min_purchase": str(coupon.min_purchase),
                "eligible": eligible,
                "shortfall": str(max(coupon.min_purchase - subtotal, Decimal("0.00"))),
            }
        )

    return JsonResponse(
        {"success": True, "coupons": data, "has_applied_coupon": has_applied_coupon}
    )