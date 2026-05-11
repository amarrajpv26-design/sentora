from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from .models import Cart as CartModel, CartItem

@receiver(user_logged_in)
def merge_cart(sender, user, request, **kwargs):
    session_cart = request.session.get(settings.CART_SESSION_ID)
    if session_cart:
        db_cart, _ = CartModel.objects.get_or_create(user=user)
        for variant_id, data in session_cart.items():
            item, created = CartItem.objects.get_or_create(cart=db_cart, variant_id=variant_id)
            # Merge quantities if item already exists in DB
            if not created:
                item.quantity += data['quantity']
            else:
                item.quantity = data['quantity']
            item.save()
        
        # Wipe the session cart so it doesn't double up
        del request.session[settings.CART_SESSION_ID]