from decimal import Decimal
from django.conf import settings
from products.models import ProductVariant
from .models import Cart as CartModel, CartItem


class Cart:
    def __init__(self, request):
        self.request = request
        self.session = request.session
        self.user = request.user

        if self.user.is_authenticated:
            
            self.cart_obj, _ = CartModel.objects.get_or_create(user=self.user)
        else:
            
            self.cart = self.session.get(settings.CART_SESSION_ID, {})
            self.session[settings.CART_SESSION_ID] = self.cart


    def add(self, variant, quantity=1, override_quantity=False):
    
        if not variant.product.is_active or not variant.is_active:
            return False, "This product is unavailable."

        if self.user.is_authenticated:

            existing_item = CartItem.objects.filter(
                cart=self.cart_obj, variant=variant
            ).first()

            is_new_item = existing_item is None

            if is_new_item and self.cart_obj.items.count() >= 10:
                return False, "You can only add 10 different items to the cart."

            if is_new_item:
                item = CartItem(cart=self.cart_obj, variant=variant, quantity=0)
            else:
                item = existing_item

            if override_quantity or is_new_item:
                new_qty = quantity
            else:
                new_qty = item.quantity + quantity
            
            MAX_PER_ITEM = 5

            if new_qty > MAX_PER_ITEM:
                return False, f"You can only add {MAX_PER_ITEM} of this item."


            if not override_quantity and new_qty > variant.stock:
                return False, "Not enough stock available."

            item.quantity = new_qty
            item.save()

            return True, "Added to collection."

        variant_id = str(variant.id)

        is_new_item = variant_id not in self.cart

        if is_new_item and len(self.cart) >= 10:
            return False, "You can only add 10 different items to the cart."

        if variant_id not in self.cart:
            self.cart[variant_id] = {"quantity": 0, "price": str(variant.get_price())}

        current_qty = self.cart[variant_id]["quantity"]

        if override_quantity or variant_id not in self.cart:
            new_qty = quantity
        else:
            new_qty = current_qty + quantity
        
            MAX_PER_ITEM = 5

            if new_qty > MAX_PER_ITEM:
                return False, f"You can only add {MAX_PER_ITEM} of this item."

        if new_qty > variant.stock:
            return False, "Not enough stock available."

        MAX_LIMIT = 10
        total_qty = sum(item["quantity"] for item in self.cart.values())
        total_qty = total_qty - current_qty + new_qty

        if total_qty > MAX_LIMIT:
            return False, f"Cart limit of {MAX_LIMIT} items exceeded."

        self.cart[variant_id]["quantity"] = new_qty
        self.save()
        return True, "Added to collection."

    def remove(self, variant):
        if self.user.is_authenticated:
            CartItem.objects.filter(cart=self.cart_obj, variant=variant).delete()
        else:
            variant_id = str(variant.id)
            if variant_id in self.cart:
                del self.cart[variant_id]
                self.save()

 
    def __iter__(self):

        items_list = []

        if self.user.is_authenticated:

            items = self.cart_obj.items.select_related(
                "variant__product",
                "variant__product__brand",
            ).order_by("id")

            for item in items:

                variant = item.variant
                price = variant.get_price()

                stock_issue = item.quantity > variant.stock

                is_available = (
                    variant.is_active
                    and variant.product.is_active
                    and variant.product.brand.is_active
                )

                items_list.append(
                    {
                        "variant": variant,
                        "quantity": item.quantity,
                        "price": price,
                        "total_price": price * item.quantity,
                        "is_available": is_available,
                        "stock_issue": stock_issue,
                    }
                )

        else:

            variant_ids = self.cart.keys()

            variants = ProductVariant.objects.filter(id__in=variant_ids).select_related(
                "product", "product__brand"
            )

            for variant in variants:

                cart_item = self.cart[str(variant.id)]

                quantity = cart_item["quantity"]
                price = Decimal(cart_item["price"])

                stock_issue = quantity > variant.stock

                is_available = (
                    variant.is_active
                    and variant.product.is_active
                    and variant.product.brand.is_active
                )

                items_list.append(
                    {
                        "variant": variant,
                        "quantity": quantity,
                        "price": price,
                        "total_price": price * quantity,
                        "is_available": is_available,
                        "stock_issue": stock_issue,
                    }
                )

       

        items_list.sort(
            key=lambda x: (
                not x["is_available"],
                x["stock_issue"],
            )
        )

        for item in items_list:
            yield item


    def get_total_price(self):
        total = 0

        if self.user.is_authenticated:
            items = self.cart_obj.items.select_related(
                "variant__product", "variant__product__brand"
            )

            for item in items:
                variant = item.variant

                is_available = (
                    variant.is_active
                    and variant.product.is_active
                    and variant.product.brand.is_active
                )

                if is_available:
                    total += item.quantity * variant.get_price()

            return total

        
        total = 0

        for variant_id, item in self.cart.items():
            try:
                variant = ProductVariant.objects.get(id=variant_id)

                is_available = (
                    variant.is_active
                    and variant.product.is_active
                    and variant.product.brand.is_active
                )

                if is_available:
                    total += Decimal(item["price"]) * item["quantity"]

            except ProductVariant.DoesNotExist:
                continue

        return total

    def get_quantity(self, variant):
        if self.user.is_authenticated:
            item = self.cart_obj.items.filter(variant=variant).first()
            return item.quantity if item else 0
        else:
            return self.cart.get(str(variant.id), {}).get("quantity", 0)

   
    def save(self):
        self.session.modified = True

    @property
    def has_available_items(self):

        return any(item["is_available"] and not item["stock_issue"] for item in self)

    def clear(self):
        if self.user.is_authenticated:
            self.cart_obj.items.all().delete()
        else:
            self.session[settings.CART_SESSION_ID] = {}
            self.save()



    @property
    def is_valid_for_checkout(self):
        if self.user.is_authenticated:
            items = self.cart_obj.items.select_related(
                "variant__product", "variant__product__brand"
            )

            for item in items:
                variant = item.variant

                if (
                    not variant.is_active
                    or not variant.product.is_active
                    or not variant.product.brand.is_active
                    or item.quantity > variant.stock
                ):
                    return False

        else:
            for item in self:
                variant = item["variant"]

                if (
                    not variant.is_active
                    or not variant.product.is_active
                    or not variant.product.brand.is_active
                    or item["quantity"] > variant.stock
                ):
                    return False

        return True

    def is_item_valid(self, variant):
        return (
            variant.is_active
            and variant.product.is_active
            and variant.product.brand.is_active
        )

    @property
    def has_valid_checkout_items(self):
        for item in self:
            variant = item["variant"]

            if (
                not variant.is_active
                or not variant.product.is_active
                or not variant.product.brand.is_active
            ):
                return False

            if item["quantity"] > variant.stock:
                return False

        return True

    def __len__(self):
        if self.user.is_authenticated:

            return sum(item.quantity for item in self.cart_obj.items.all())

        return sum(item["quantity"] for item in self.cart.values())
