

from decimal import Decimal
from django.utils import timezone
import uuid



def get_effective_price(variant):
    from offers.models import ProductOffer, CategoryOffer, BrandOffer
    
    base_price = variant.offer_price if variant.offer_price else variant.price
    best_price = base_price
    best_label = None
    now = timezone.now()

    # ── 1. Product-level offer ──
    product_offer = (
        ProductOffer.objects.filter(
            product=variant.product,
            is_active=True,
            start_date__lte=now,
            end_date__gte=now,
        )
        .order_by("-discount_value")
        .first()
    )
    if product_offer:
        product_offer_price = product_offer.compute_discount(variant.price)
        if product_offer_price < best_price:
            best_price = product_offer_price
            best_label = _build_label(product_offer)

    # ── 2. Category-level offers ──
    category_ids = variant.product.categories.values_list("id", flat=True)
    category_offers = CategoryOffer.objects.filter(
        category_id__in=category_ids,
        is_active=True,
        start_date__lte=now,
        end_date__gte=now,
    )
    for cat_offer in category_offers:
        cat_offer_price = cat_offer.compute_discount(variant.price)
        if cat_offer_price < best_price:
            best_price = cat_offer_price
            best_label = _build_label(cat_offer)

    # ── 3. Brand-level offer ──  ← ADD THIS BLOCK
    brand_offers = BrandOffer.objects.filter(
        brand=variant.product.brand,
        is_active=True,
        start_date__lte=now,
        end_date__gte=now,
    )
    for brand_offer in brand_offers:
        brand_offer_price = brand_offer.compute_discount(variant.price)
        if brand_offer_price < best_price:
            best_price = brand_offer_price
            best_label = _build_label(brand_offer)

    return best_price, best_label


def _build_label(offer):
    if offer.discount_type == "PERCENTAGE":
        return f"{offer.name} (-{offer.discount_value:.0f}%)"
    else:
        return f"{offer.name} (-₹{offer.discount_value:.0f})"


def get_cart_item_price(variant):
    """Convenience wrapper — returns just the effective price."""
    price, _ = get_effective_price(variant)
    return price


def apply_referral_offer(referral_offer, referee_user):
    """
    Grants wallet credit to the referee after their first order.
    Called from order placement logic.
    Returns True if reward was granted.
    """
    from offers.models import ReferralUsage
    from wallets.models import Wallet, WalletTransaction

    if not referral_offer.is_active or referral_offer.is_exhausted:
        return False

    usage, created = ReferralUsage.objects.get_or_create(
        referral_offer=referral_offer,
        referee=referee_user,
    )

    if not created and usage.reward_granted:
        return False  # already rewarded

    # Grant referee reward
    if referral_offer.referee_reward_type == "WALLET_CREDIT":
        wallet, _ = Wallet.objects.get_or_create(user=referee_user)
        wallet.balance += referral_offer.referee_reward_value
        wallet.save()
        WalletTransaction.objects.create(
            wallet=wallet,
            amount=referral_offer.referee_reward_value,
            transaction_type="CREDIT",
            purpose="REFERRAL_BONUS",
            description=f"Referral bonus from {referral_offer.referrer.username}",
        )

    # Grant referrer reward
    if referral_offer.referrer_reward_type == "WALLET_CREDIT":
        referrer_wallet, _ = Wallet.objects.get_or_create(
            user=referral_offer.referrer
        )
        referrer_wallet.balance += referral_offer.referrer_reward_value
        referrer_wallet.save()
        WalletTransaction.objects.create(
            wallet=referrer_wallet,
            amount=referral_offer.referrer_reward_value,
            transaction_type="CREDIT",
            purpose="REFERRAL_BONUS",
            description=f"Referral reward — {referee_user.username} signed up using your link",
        )

    usage.reward_granted = True
    usage.save()
    return True

# offers/utils.py — add below your existing apply_referral_offer()

REFERRAL_AUTO_UNLOCK_THRESHOLD = Decimal("10000.00")


def get_qualifying_orders(user):
    """
    Orders that count as real, committed purchases for referral/loyalty
    purposes — excludes cancelled orders and online orders that were
    never actually paid for.
    """
    from orders.models import Order

    return (
        Order.objects.filter(user=user)
        .exclude(order_status="CANCELLED")
        .exclude(payment_method="ONLINE", payment_status__in=["PENDING", "FAILED"])
    )


def apply_referral_to_new_user(new_user, referral_input):
    """
    Called once, at signup, with whatever the new user typed/arrived with
    (a referral_code like 'AMAR50' or a token UUID from the link).
    Links new_user.referred_by — does NOT grant any reward yet.
    """
    from offers.models import ReferralOffer

    if not referral_input:
        return False

    referral_offer = None
    try:
        token = uuid.UUID(referral_input)
        referral_offer = ReferralOffer.objects.filter(token=token, is_active=True).first()
    except (ValueError, AttributeError, TypeError):
        pass

    if not referral_offer:
        referral_offer = ReferralOffer.objects.filter(
            referral_code__iexact=referral_input, is_active=True
        ).first()

    if not referral_offer or referral_offer.is_exhausted:
        return False

    if referral_offer.referrer_id == new_user.id:
        return False  # can't refer yourself

    new_user.referred_by = referral_offer.referrer
    new_user.save(update_fields=["referred_by"])
    return True


def maybe_auto_unlock_referral(user):
    """
    Auto-creates a ReferralOffer for `user` (with default reward values)
    the moment their lifetime qualifying spend crosses ₹10,000.
    No-ops if they already have one — admin-created or auto-created.
    """
    from offers.models import ReferralOffer
    from django.db.models import Sum

    if ReferralOffer.objects.filter(referrer=user).exists():
        return None

    total_spent = get_qualifying_orders(user).aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0.00")

    if total_spent < REFERRAL_AUTO_UNLOCK_THRESHOLD:
        return None

    return ReferralOffer.objects.create(referrer=user)


def grant_referral_reward_if_first_order(order):
    """
    If order.user was referred by someone, and this is their first
    qualifying order, grants the reward to both sides.
    Safe to call on every successful order: apply_referral_offer() is
    idempotent, and the "first order" check here prevents re-firing too.
    """
    from offers.models import ReferralOffer

    user = order.user
    if not user.referred_by_id:
        return False

    if get_qualifying_orders(user).exclude(pk=order.pk).exists():
        return False  # not their first qualifying order

    try:
        referral_offer = ReferralOffer.objects.get(referrer_id=user.referred_by_id)
    except ReferralOffer.DoesNotExist:
        return False

    return apply_referral_offer(referral_offer, user)


def handle_order_referral_events(order):
    """Single entry point — call this once, right when an order succeeds."""
    grant_referral_reward_if_first_order(order)
    maybe_auto_unlock_referral(order.user)
