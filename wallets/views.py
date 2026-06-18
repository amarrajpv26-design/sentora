from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import get_user_model
from wallets.models import WalletTransaction, Wallet
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal
import razorpay
from django.conf import settings
import json
from django.http import JsonResponse
from django.core.paginator import Paginator

User = get_user_model()


@login_required
def wallet_view(request):
    wallet, created = Wallet.objects.get_or_create(user=request.user)

    transaction_type = request.GET.get("type", "ALL")

    transactions = wallet.transactions.all().order_by("-created_at")

    if transaction_type == "CREDIT":
        transactions = transactions.filter(transaction_type="CREDIT")

    elif transaction_type == "DEBIT":
        transactions = transactions.filter(transaction_type="DEBIT")

    paginator = Paginator(transactions, 10)

    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "wallets/wallet.html",
        {
            "wallet": wallet,
            "page_obj": page_obj,
            "selected_type": transaction_type,
        },
    )


@login_required
def wallet_recharge_view(request):

    if request.method != "POST":
        return render(request, "wallets/recharge_payment.html")

    amount_str = request.POST.get("amount")

    # ---------------------------
    # SAFE CONVERSION
    # ---------------------------
    try:
        amount = int(amount_str)
    except (TypeError, ValueError):
        messages.error(request, "Invalid amount entered.")
        return redirect("wallet")

    # ---------------------------
    # VALIDATION RULES
    # ---------------------------
    if amount < 100:
        messages.error(request, "Minimum recharge amount is ₹100.")
        return redirect("wallet")

    if amount > 50000:
        messages.error(request, "Maximum recharge allowed is ₹50,000 per transaction.")
        return redirect("wallet")

    # ---------------------------
    # RAZORPAY CLIENT
    # ---------------------------
    client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )

    try:
        razorpay_order = client.order.create(
            {
                "amount": amount * 100,
                "currency": "INR",
                "notes": {"user_id": str(request.user.id)},
            }
        )
    except Exception:
        messages.error(request, "Payment gateway error. Please try again.")
        return redirect("wallet")

    # ---------------------------
    # SESSION TRACKING (UNCHANGED)
    # ---------------------------
    request.session[f"wallet_order_{razorpay_order['id']}"] = request.user.id

    # ---------------------------
    # TEMPLATE CONTEXT (UNCHANGED)
    # ---------------------------
    context = {
        "razorpay_key": settings.RAZORPAY_KEY_ID,
        "razorpay_order": razorpay_order["id"],
        "amount": amount,
        "amount_paise": amount * 100,
    }

    return render(request, "wallets/recharge_payment.html", context)


@csrf_exempt
@transaction.atomic
def wallet_payment_success(request):

    if request.method != "POST":
        return redirect("wallet")

    payment_id = request.POST.get("razorpay_payment_id")
    order_id = request.POST.get("razorpay_order_id")
    signature = request.POST.get("razorpay_signature")

    client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )

    # -----------------------------------------
    # STEP 1: VERIFY SIGNATURE (UNCHANGED)
    # -----------------------------------------
    try:
        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": signature,
            }
        )
    except Exception:
        messages.error(request, "Payment verification failed.")
        return redirect("wallet")

    # -----------------------------------------
    # STEP 2: FETCH ORDER + USER (UNCHANGED)
    # -----------------------------------------
    try:
        order = client.order.fetch(order_id)
        user_id = order["notes"]["user_id"]
        user = User.objects.get(id=user_id)
    except Exception:
        messages.error(request, "Invalid payment data.")
        return redirect("wallet")

    # -----------------------------------------
    # STEP 3: IDENTITY CHECK (NEW - IMPORTANT)
    # Prevent double processing of SAME payment
    # -----------------------------------------
    if WalletTransaction.objects.filter(razorpay_payment_id=payment_id).exists():
        messages.warning(request, "Payment already processed.")
        return redirect("wallet")

    # -----------------------------------------
    # STEP 4: GET AMOUNT (UNCHANGED LOGIC)
    # -----------------------------------------
    amount = Decimal(order["amount"]) / 100

    # -----------------------------------------
    # STEP 5: CREDIT WALLET (SAFE)
    # -----------------------------------------
    wallet, _ = Wallet.objects.get_or_create(user=user)
    wallet.balance += amount
    wallet.save()

    WalletTransaction.objects.create(
        wallet=wallet,
        razorpay_payment_id=payment_id,  # IMPORTANT for uniqueness
        amount=amount,
        transaction_type="CREDIT",
        purpose="RECHARGE",
        description="Wallet Recharge",
    )

    messages.success(request, f"₹{amount} added to wallet successfully!")
    return redirect("wallet")


@login_required
def create_wallet_order(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    try:
        data = json.loads(request.body)
        amount = int(data.get("amount", 0))
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid amount"}, status=400)

    if amount < 100 or amount > 50000:
        return JsonResponse({"error": "Amount out of range"}, status=400)

    client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )
    try:
        order = client.order.create(
            {
                "amount": amount * 100,
                "currency": "INR",
                "notes": {"user_id": str(request.user.id)},
            }
        )
    except Exception:
        return JsonResponse({"error": "Gateway error"}, status=500)

    return JsonResponse(
        {
            "order_id": order["id"],
            "amount_paise": amount * 100,
            "key": settings.RAZORPAY_KEY_ID,
        }
    )
