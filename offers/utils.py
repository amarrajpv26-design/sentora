

from decimal import Decimal
from django.utils import timezone


def get_effective_price(variant):
    """
    Returns (effective_price, offer_label) for a ProductVariant.
    offer_label is a human-readable string like "Summer Sale (-20%)" or None.
    """
    from offers.models import ProductOffer, CategoryOffer

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
        .order_by("-discount_value")  # highest discount first
        .first()
    )

    if product_offer:
        product_offer_price = product_offer.compute_discount(variant.price)
        if product_offer_price < best_price:
            best_price = product_offer_price
            best_label = _build_label(product_offer)

    # ── 2. Category-level offers (all categories this product is in) ──
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