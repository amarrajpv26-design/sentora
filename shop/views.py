from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Min, Sum, Q
from django.core.paginator import Paginator
from products.models import Product, Category, Brand
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from cart.models import Wishlist


@login_required(login_url="user_login")
def product_list(request):
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

    from cart.models import Wishlist

    wishlist_variant_ids = Wishlist.objects.filter(user=request.user).values_list(
        "items__variant__id", flat=True
    )

    wishlist_product_ids = Product.objects.filter(
        variants__id__in=wishlist_variant_ids
    ).values_list("id", flat=True)

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


def product_detail(request, product_id):
    product = get_object_or_404(
        Product.objects.prefetch_related("images", "variants", "categories"),
        id=product_id,
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

    variant_stats = active_variants.aggregate(
        min_price=Min("price"), min_offer=Min("offer_price"), total_stock=Sum("stock")
    )

    total_stock = variant_stats["total_stock"] or 0
    min_price = variant_stats["min_price"]
    offer_price = variant_stats["min_offer"]

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

    context = {
        "product": product,
        "related_products": related_products,
        "variants": active_variants.order_by("price"),
        "min_price": min_price,
        "offer_price": offer_price,
        "total_stock": total_stock,
        "is_low_stock": is_low_stock,
        'is_in_wishlist': is_in_wishlist,
        "all_categories": Category.objects.filter(is_active=True),
    }

    return render(request, "shop/product_detail.html", context)
