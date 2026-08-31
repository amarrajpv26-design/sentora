from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Min, Sum, Q, Prefetch
from django.core.paginator import Paginator
from products.models import Product, Category, Brand
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from products.models import Brand
from cart.models import Wishlist, WishlistItem
from reviews.models import Review
from orders.models import OrderItem
from offers.utils import get_effective_price
from django.db.models.functions import Coalesce
from django.db.models import Avg
from django.db.models import (
    Min,
    Sum,
    Q,
    Prefetch,
    Count,
    F,
    DecimalField,
    ExpressionWrapper,
)


def product_list(request):
    # NOTE: min_price is annotated here so it can be used for filtering
    # and sorting below. This is the MRP-based minimum (variant.price),
    # not the offer-adjusted price — offer pricing is applied separately
    # below for display purposes only.
    products = Product.objects.filter(is_active=True).annotate(
        min_price=Min("variants__price")
    )

    query = request.GET.get("q", "").strip()

    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(brand__name__icontains=query)
            | Q(top_notes__icontains=query)
        )

    category_id = request.GET.get("category", "").strip()
    brand_id = request.GET.get("brand", "").strip()
    min_price = request.GET.get("min_price", "").strip()
    max_price = request.GET.get("max_price", "").strip()

    if category_id:
        products = products.filter(categories__id=category_id)

    if brand_id:
        products = products.filter(brand_id=brand_id)

    if min_price:
        try:
            products = products.filter(min_price__gte=float(min_price))
        except ValueError:
            pass

    if max_price:
        try:
            products = products.filter(min_price__lte=float(max_price))
        except ValueError:
            pass

    products = products.distinct()

    sort = request.GET.get("sort", "newest")

    sort_options = {
        "price_low": "min_price",
        "price_high": "-min_price",
        "name_az": "name",
        "name_za": "-name",
        "newest": "-created_at",
    }

    products = products.order_by(sort_options.get(sort, "-created_at"))

    paginator = Paginator(products, 12)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # ---------------- Offer-aware display pricing ----------------
    # For each product on this page, compute:
    #   display_min_price   -> lowest MRP across active variants
    #   display_offer_price -> lowest effective price (after product/
    #                           category offers) across active variants
    #   has_offer            -> True if an offer actually lowers the price
    for product in page_obj:
        variants = list(product.variants.filter(is_active=True))

        base_prices = [v.price for v in variants]
        effective_prices = [get_effective_price(v)[0] for v in variants]

        product.display_min_price = (
            min(base_prices) if base_prices else (product.min_price or 0)
        )
        product.display_offer_price = (
            min(effective_prices) if effective_prices else product.display_min_price
        )
        product.has_offer = product.display_offer_price < product.display_min_price
    # ---------------------------------------------------------------

    if request.user.is_authenticated:
        wishlist_variant_ids = WishlistItem.objects.filter(
            wishlist__user=request.user
        ).values_list("variant_id", flat=True)
        wishlist_product_ids = Product.objects.filter(
            variants__id__in=wishlist_variant_ids
        ).values_list("id", flat=True)
        wishlist_variant_ids = set(wishlist_variant_ids)
    else:
        wishlist_variant_ids = set()
        wishlist_product_ids = []

    context = {
        "products": page_obj,
        "categories": Category.objects.filter(is_active=True),
        "brands": Brand.objects.filter(is_active=True),
        "current_params": request.GET,
        "query": query,
        "selected_category": category_id,
        "selected_brand": brand_id,
        "selected_min_price": min_price,
        "selected_max_price": max_price,
        "wishlist_variant_ids": wishlist_variant_ids,
        "wishlist_product_ids": wishlist_product_ids,
        "selected_sort": sort,
    }

    return render(request, "shop/product_list.html", context)


def product_detail(request, product_uuid):
    product = get_object_or_404(
        Product.objects.prefetch_related("images", "variants", "categories"),
        uuid=product_uuid,
    )

    if not product.is_active:
        messages.error(
            request, "This essence is currently unavailable or has been archived."
        )
        return redirect("shop:product_list")

    active_variants = product.variants.filter(is_active=True)

    if not active_variants.exists():
        messages.error(request, "This essence is currently unavailable.")
        return redirect("shop:product_list")

    variant_stats = active_variants.aggregate(total_stock=Sum("stock"))

    total_stock = variant_stats["total_stock"] or 0

    variant_prices = []

    for variant in active_variants:
        effective_price, label = get_effective_price(variant)

        variant.original_price = variant.price
        variant.effective_price = effective_price
        variant.offer_label = label

        variant_prices.append(
            {
                "original_price": variant.price,
                "effective_price": effective_price,
            }
        )

    min_price = min(v["original_price"] for v in variant_prices)
    offer_price = min(v["effective_price"] for v in variant_prices)
    variants = sorted(active_variants, key=lambda v: v.price)
    product_category_ids = product.categories.values_list("id", flat=True)

    related_products = (
        Product.objects.filter(categories__id__in=product_category_ids, is_active=True)
        .exclude(id=product.id)
        .distinct()[:4]
    )

    low_stock_threshold = 5
    is_low_stock = 0 < total_stock <= low_stock_threshold

    is_in_wishlist = False

    if request.user.is_authenticated:
        is_in_wishlist = Wishlist.objects.filter(
            user=request.user, items__variant__product=product
        ).exists()

    reviews = Review.objects.filter(product=product, is_approved=True).select_related(
        "user"
    )
    review_count = reviews.count()

    average_rating = reviews.aggregate(avg=Avg("rating"))["avg"] or 0

    can_review = False
    if request.user.is_authenticated:
        can_review = (
            OrderItem.objects.filter(
                order__user=request.user,
                product_variant__product=product,
                item_status="ACTIVE",
                order__order_status__in=["DELIVERED", "RETURN_REJECTED"],
            )
            .exclude(review__isnull=False)
            .exists()
        )

    context = {
        "product": product,
        "related_products": related_products,
        "variants": variants,
        "min_price": min_price,
        "offer_price": offer_price,
        "total_stock": total_stock,
        "is_low_stock": is_low_stock,
        "is_in_wishlist": is_in_wishlist,
        "all_categories": Category.objects.filter(is_active=True),
        "reviews": reviews,
        "review_count": review_count,
        "average_rating": average_rating,
        "can_review": can_review,
    }

    return render(request, "shop/product_detail.html", context)


def brand_list(request):

    first_image_qs = Product.objects.prefetch_related("images").order_by("id")

    brands = (
        Brand.objects.filter(is_active=True)
        .order_by("id")  # oldest added first
        .prefetch_related(Prefetch("products", queryset=first_image_qs))
    )

    return render(request, "shop/brand_list.html", {"brands": brands})


def new_arrivals(request):

    products = (
        Product.objects.filter(is_active=True)
        .annotate(min_price=Min("variants__price"))
        .order_by("-created_at")[:9]  # only latest 9
    )

    for product in products:
        variants = list(product.variants.filter(is_active=True))

        base_prices = [v.price for v in variants]
        effective_prices = [get_effective_price(v)[0] for v in variants]

        product.display_min_price = (
            min(base_prices) if base_prices else (product.min_price or 0)
        )

        product.display_offer_price = (
            min(effective_prices) if effective_prices else product.display_min_price
        )

        product.has_offer = product.display_offer_price < product.display_min_price

    if request.user.is_authenticated:
        wishlist_variant_ids = set(
            WishlistItem.objects.filter(wishlist__user=request.user).values_list(
                "variant_id", flat=True
            )
        )
    else:
        wishlist_variant_ids = set()

    return render(
        request,
        "shop/new_arrivals.html",
        {
            "products": products,
            "wishlist_variant_ids": wishlist_variant_ids,
        },
    )


def category_list(request):

    first_product_qs = Product.objects.prefetch_related("images").order_by("id")

    categories = (
        Category.objects.filter(is_active=True)
        .order_by("id")  # oldest created first
        .prefetch_related(Prefetch("products", queryset=first_product_qs))
    )

    return render(request, "shop/category_list.html", {"categories": categories})


def category_products(request, slug):
    category = get_object_or_404(Category, slug=slug)

    products = category.products.filter(is_active=True).prefetch_related(
        "images", "variants"
    )

    # Same offer-aware display pricing as product_list, kept consistent
    # so category pages show the same effective price as the main shop.
    for product in products:
        variants = list(product.variants.filter(is_active=True))

        base_prices = [v.price for v in variants]
        effective_prices = [get_effective_price(v)[0] for v in variants]

        product.display_min_price = min(base_prices) if base_prices else 0
        product.display_offer_price = (
            min(effective_prices) if effective_prices else product.display_min_price
        )
        product.has_offer = product.display_offer_price < product.display_min_price

    return render(
        request,
        "shop/category_products.html",
        {
            "category": category,
            "products": products,
        },
    )


def best_sellers(request):
    # Determine the sorting and filtering mode chosen by the user
    mode = request.GET.get("mode", "qty")
    if mode not in ["qty", "orders", "revenue"]:
        mode = "qty"

    # Only aggregate active items from valid/non-cancelled customer orders
    valid_items = Q(variants__orderitem__item_status="ACTIVE") & ~Q(
        variants__orderitem__order__order_status="CANCELLED"
    )

    # 1. Annotate metrics onto the active products
    products = Product.objects.filter(is_active=True).annotate(
        min_price=Min("variants__price"),
        total_qty_sold=Coalesce(
            Sum("variants__orderitem__quantity", filter=valid_items), 0
        ),
        order_count=Coalesce(
            Count("variants__orderitem__order", distinct=True, filter=valid_items), 0
        ),
        revenue=Coalesce(
            Sum(
                ExpressionWrapper(
                    F("variants__orderitem__quantity")
                    * F("variants__orderitem__price"),
                    output_field=DecimalField(),
                ),
                filter=valid_items,
            ),
            0,
            output_field=DecimalField(),
        ),
    )

    # 2. Apply strict baseline thresholds required for Best Sellers
    products = products.filter(
        total_qty_sold__gte=5, order_count__gte=5, revenue__gte=20000
    )

    # 3. Sort dynamically based on the active mode focus
    if mode == "orders":
        products = products.order_by("-order_count", "-created_at")
    elif mode == "revenue":
        products = products.order_by("-revenue", "-created_at")
    else:  # 'qty' is the fallback default
        products = products.order_by("-total_qty_sold", "-created_at")

    # 4. Fetch the top 10 qualified best sellers
    products = products[:10]

    # Calculate active pricing profiles and offer states for the top 10 items
    for product in products:
        variants = list(product.variants.filter(is_active=True))
        base_prices = [v.price for v in variants]
        effective_prices = [get_effective_price(v)[0] for v in variants]

        product.display_min_price = (
            min(base_prices) if base_prices else (product.min_price or 0)
        )
        product.display_offer_price = (
            min(effective_prices) if effective_prices else product.display_min_price
        )
        product.has_offer = product.display_offer_price < product.display_min_price

    context = {
        "products": products,
        "mode": mode,
    }
    return render(request, "shop/best_sellers.html", context)


def archive_collection(request):
    # Fetch all products that are archived (is_active=False)
    products = (
        Product.objects.filter(is_active=False)
        .annotate(min_price=Min("variants__price"))
        .order_by("-id")
    )  # Shows newest additions to archive first

    # Calculate active pricing profiles for the archived pieces
    for product in products:
        # Note: We look at all variants for the archive card layout
        variants = list(product.variants.all())
        base_prices = [v.price for v in variants]
        effective_prices = [get_effective_price(v)[0] for v in variants]

        product.display_min_price = (
            min(base_prices) if base_prices else (product.min_price or 0)
        )
        product.display_offer_price = (
            min(effective_prices) if effective_prices else product.display_min_price
        )
        product.has_offer = product.display_offer_price < product.display_min_price

    # Retrieve wishlist profiles for structural synergy with your layout design
    if request.user.is_authenticated:
        wishlist_variant_ids = set(
            WishlistItem.objects.filter(wishlist__user=request.user).values_list(
                "variant_id", flat=True
            )
        )
    else:
        wishlist_variant_ids = set()

    context = {
        "products": products,
        "wishlist_variant_ids": wishlist_variant_ids,
    }
    return render(request, "shop/archive_collection.html", context)
