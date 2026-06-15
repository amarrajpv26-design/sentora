from allauth.account.signals import user_signed_up
from django.dispatch import receiver
 
@receiver(user_signed_up)
def handle_referral_on_signup(request, user, **kwargs):
    token = request.session.get('referral_token')
    if not token:
        return
    from offers.models import ReferralOffer
    from offers.utils import apply_referral_offer
    try:
        offer = ReferralOffer.objects.get(token=token, is_active=True)
        if offer.referrer != user:  # can't refer yourself
            apply_referral_offer(offer, user)
    except ReferralOffer.DoesNotExist:
        pass
    finally:
        request.session.pop('referral_token', None)