from .models import Wishlist, WishlistItem


class WishlistManager:
    def __init__(self, request):
        self.user = request.user

        self.wishlist_obj = None
        if self.user.is_authenticated:
            self.wishlist_obj, _ = Wishlist.objects.get_or_create(user=self.user)

    def add(self, variant):
        if not self.user.is_authenticated:
            return False, "Login required"

        item, created = WishlistItem.objects.get_or_create(
            wishlist=self.wishlist_obj, variant=variant
        )
        return created, "Added to Wishlist"

    def remove(self, variant):
        if not self.user.is_authenticated:
            return False, "Login required"

        WishlistItem.objects.filter(
            wishlist=self.wishlist_obj, variant=variant
        ).delete()

        return True, "Removed from Wishlist"

    def toggle(self, variant):
        item = WishlistItem.objects.filter(
            wishlist=self.wishlist_obj, variant=variant
        ).first()

        if item:
            item.delete()
            return False, "Removed from Wishlist"
        else:
            WishlistItem.objects.create(wishlist=self.wishlist_obj, variant=variant)
            return True, "Added to Wishlist"

    def __iter__(self):
        if self.user.is_authenticated and self.wishlist_obj:
            items = self.wishlist_obj.items.select_related("variant__product")
            for item in items:
                yield item.variant

    def count(self):
        if not self.user.is_authenticated or not self.wishlist_obj:
            return 0

        return WishlistItem.objects.filter(wishlist=self.wishlist_obj).count()
