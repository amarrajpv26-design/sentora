from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.cache import never_cache
from .models import Category, Product, Brand, ProductVariant, ProductImage
from .forms import CategoryForm
import base64
from django.utils.text import slugify
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
import uuid

# ──────────────────────────────────────────────
#  CATEGORY VIEWS  (unchanged)
# ──────────────────────────────────────────────


@staff_member_required(login_url="admin_login")
@never_cache
def admin_category_list(request):
    categories_list = Category.objects.filter(is_active=True).order_by("-created_at")

    active_count = Category.objects.filter(is_active=True).count()
    featured_count = Category.objects.filter(is_featured=True).count()
    archived_count = Category.objects.filter(is_active=False).count()

    search_query = request.GET.get("search", "")
    status_filter = request.GET.get("status", "all")

    if search_query:
        categories_list = categories_list.filter(Q(name__istartswith=search_query))
    if status_filter == "active":
        categories_list = categories_list.filter(is_active=True)
    elif status_filter == "archived":
        categories_list = categories_list.filter(is_active=False)

    paginator = Paginator(categories_list, 5)
    page_number = request.GET.get("page")
    categories = paginator.get_page(page_number)

    return render(
        request,
        "products/admin_category_list.html",
        {
            "categories": categories,
            "search_query": search_query,
            "status_filter": status_filter,
            "active_count": active_count,
            "featured_count": featured_count,
            "archived_count": archived_count,
        },
    )


@staff_member_required(login_url="admin_login")
def add_category(request):
    if request.method == "POST":
        form = CategoryForm(request.POST, request.FILES)
        cropped_data = request.POST.get("cropped_image")

        if form.is_valid():
            category = form.save(commit=False)
            category.name = category.name.strip().capitalize()

            if Category.objects.filter(name__iexact=category.name).exists():
                form.add_error("name", f"The vault '{category.name}' already exists.")
                return render(
                    request, "products/admin_add_category.html", {"form": form}
                )

            if cropped_data:
                try:
                    format, imgstr = cropped_data.split(";base64,")
                    ext = format.split("/")[-1]
                    data = ContentFile(
                        base64.b64decode(imgstr), name=f"{category.name}.{ext}"
                    )
                    category.category_image = data
                except (ValueError, IndexError):
                    messages.error(request, "Invalid image data received.")
                    return render(
                        request, "products/admin_add_category.html", {"form": form}
                    )

            try:
                category.save()
                messages.success(
                    request, f"Vault '{category.name}' established successfully."
                )
                return redirect("admin_category_list")
            except ValidationError as e:
                messages.error(request, e.message)
                return render(
                    request, "products/admin_add_category.html", {"form": form}
                )
    else:
        form = CategoryForm()

    return render(
        request,
        "products/admin_add_category.html",
        {"form": form, "title": "Add New Category"},
    )


@staff_member_required(login_url="admin_login")
def edit_category(request, category_id):
    category = get_object_or_404(Category, pk=category_id)

    if request.method == "POST":
        form = CategoryForm(request.POST, request.FILES, instance=category)
        cropped_data = request.POST.get("cropped_image")

        if form.is_valid():
            updated_category = form.save(commit=False)
            updated_category.name = updated_category.name.strip().capitalize()

            if (
                Category.objects.filter(name__iexact=updated_category.name)
                .exclude(pk=category.pk)
                .exists()
            ):
                form.add_error(
                    "name", f"The vault '{updated_category.name}' already exists."
                )
                return render(
                    request,
                    "products/admin_edit_category.html",
                    {"form": form, "category": category},
                )

            if cropped_data:
                try:
                    format, imgstr = cropped_data.split(";base64,")
                    ext = format.split("/")[-1]
                    data = ContentFile(
                        base64.b64decode(imgstr), name=f"{updated_category.name}.{ext}"
                    )
                    updated_category.category_image = data
                except (ValueError, IndexError):
                    messages.error(request, "Invalid visual data.")
                    return render(
                        request,
                        "products/admin_edit_category.html",
                        {"form": form, "category": category},
                    )

            try:
                updated_category.save()
                messages.success(
                    request, f"Vault '{updated_category.name}' updated successfully."
                )
                return redirect("admin_category_list")
            except ValidationError as e:
                messages.error(request, e.message)
                return render(
                    request,
                    "products/admin_edit_category.html",
                    {"form": form, "category": category},
                )
    else:
        form = CategoryForm(instance=category)

    return render(
        request,
        "products/admin_edit_category.html",
        {"form": form, "category": category, "title": f"Edit {category.name}"},
    )


@staff_member_required(login_url="admin_login")
def toggle_category_status(request, category_id):
    category = get_object_or_404(Category, id=category_id)
    category.is_active = not category.is_active
    category.save()

    if not category.is_active:
        # Archive ALL active products in this category
        for product in category.products.filter(is_active=True):
            product.is_active = False
            product.save()
    else:
        # Restore products that were archived because of this category,
        # but only if none of their OTHER categories are still archived
        for product in category.products.filter(is_active=False):
            if product.categories.filter(is_active=False).count() == 0:
                product.is_active = True
                product.save()

    status = "activated" if category.is_active else "unlisted (soft-deleted)"
    messages.success(request, f"Category '{category.name}' has been {status}.")
    referer = request.META.get("HTTP_REFERER", "")
    if "archive" in referer:
        return redirect("/products/admin/archive/?tab=categories")
    return redirect("admin_category_list")


@staff_member_required(login_url="admin_login")
def toggle_product_status(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    if not product.is_active:
        # Trying to UNARCHIVE — block if any of its categories are archived
        archived_categories = product.categories.filter(is_active=False)
        if archived_categories.exists():
            names = ", ".join(c.name for c in archived_categories)
            messages.error(
                request,
                f"Cannot unarchive '{product.name}': its category '{names}' is archived. "
                f"Unarchive the category first.",
            )
            referer = request.META.get("HTTP_REFERER", "")
            if "archive" in referer:
                return redirect("/products/admin/archive/?tab=products")
            return redirect("admin_product_list")

    product.is_active = not product.is_active
    product.save()
    status = "listed" if product.is_active else "unlisted (soft-deleted)"
    messages.success(request, f"Product '{product.name}' status set to {status}.")
    referer = request.META.get("HTTP_REFERER", "")
    if "archive" in referer:
        return redirect("/products/admin/archive/?tab=products")
    return redirect("admin_product_list")


# ──────────────────────────────────────────────
#  PRODUCT VIEWS
# ──────────────────────────────────────────────


@staff_member_required(login_url="admin_login")
@never_cache
def admin_product_list(request):
    products_list = (
        Product.objects.filter(is_active=True)
        .select_related("brand")
        .prefetch_related("categories", "variants")
        .order_by("-created_at")
    )

    # FIX: These counts were missing from the original view
    active_count = Product.objects.filter(is_active=True).count()
    featured_count = Product.objects.filter(is_featured=True).count()
    archived_count = Product.objects.filter(is_active=False).count()

    search_query = request.GET.get("search", "")
    brand_filter = request.GET.get("brand", "all")
    category_filter = request.GET.get("category", "all")

    if search_query:
        products_list = products_list.filter(
            Q(name__icontains=search_query) | Q(brand__name__icontains=search_query)
        )

    if brand_filter != "all":
        products_list = products_list.filter(brand_id=brand_filter)
    if category_filter != "all":
        products_list = products_list.filter(categories__id=category_filter)

    products_list = products_list.distinct()

    paginator = Paginator(products_list, 6)
    page_number = request.GET.get("page")
    products = paginator.get_page(page_number)
    brands = Brand.objects.all().order_by("name")
    categories = Category.objects.filter(is_active=True).order_by("name")

    return render(
        request,
        "products/admin_product_list.html",
        {
            "products": products,
            "brands": brands,
            "categories": categories,
            "search_query": search_query,
            "brand_filter": brand_filter,
            "category_filter": category_filter,
            "active_count": active_count,
            "featured_count": featured_count,
            "archived_count": archived_count,
        },
    )


@staff_member_required(login_url="admin_login")
def product_detail(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    variants = product.variants.all().order_by("size_ml")
    gallery = product.images.all()
    return render(
        request,
        "products/admin_product_detail.html",
        {
            "product": product,
            "variants": variants,
            "gallery": gallery,
        },
    )


def _get_or_create_brand(brand_input):
    """
    FIX: The original code used `name__iexact` as a get_or_create lookup kwarg,
    which Django treats as a literal field lookup — it won't match case-insensitively
    and can create duplicate Brand rows. This helper does it correctly.
    """
    brand_input = brand_input.strip()
    try:
        return Brand.objects.get(name__iexact=brand_input)
    except Brand.DoesNotExist:
        return Brand.objects.create(
            name=brand_input.title(),
            slug=slugify(brand_input),
        )


def _validate_variants_server(sizes, prices, offers):
    """
    Shared server-side variant validation.
    Returns a list of error strings; empty list means valid.

    Rules:
      1. No duplicate sizes.
      2. For each variant: offer (if set) must be strictly less than price.
      3. Variants sorted by size_ml must have strictly increasing prices AND
         strictly increasing offers (when both adjacent variants have an offer).
    """
    SIZE_ORDER = {"8ml": 8, "20ml": 20, "50ml": 50, "100ml": 100}
    errors = []

    # Parse into structured list; skip completely empty rows
    variants = []
    seen_sizes = set()

    for i in range(len(sizes)):
        size = sizes[i].strip() if i < len(sizes) else ""
        price_raw = prices[i].strip() if i < len(prices) else ""
        offer_raw = offers[i].strip() if i < len(offers) else ""

        if not size or not price_raw:
            continue  # empty row — skip

        # Rule 1: duplicate size
        if size in seen_sizes:
            errors.append(
                f"Duplicate variant: '{size}' can only be added once per product."
            )
            continue
        seen_sizes.add(size)

        try:
            price = float(price_raw)
        except ValueError:
            errors.append(f"Invalid price for {size}.")
            continue

        offer = None
        if offer_raw:
            try:
                parsed_offer = float(offer_raw)
            except ValueError:
                errors.append(f"Invalid offer price for {size}.")
                continue
            if parsed_offer > 0:
                offer = parsed_offer

        # Rule 2: offer < price for this variant
        if offer is not None and offer >= price:
            errors.append(
                f"{size}: Offer price (₹{offer:.0f}) must be less than the regular price (₹{price:.0f})."
            )

        variants.append(
            {
                "size": size,
                "order": SIZE_ORDER.get(size, 999),
                "price": price,
                "offer": offer,
            }
        )

    if errors:
        return errors

    # Sort by size order for cross-variant comparison
    variants.sort(key=lambda v: v["order"])

    # Rule 3: strictly increasing price AND offer across sizes
    for i in range(1, len(variants)):
        prev = variants[i - 1]
        curr = variants[i]

        if curr["price"] <= prev["price"]:
            errors.append(
                f"{curr['size']} price (₹{curr['price']:.0f}) must be greater than "
                f"{prev['size']} price (₹{prev['price']:.0f})."
            )

        # If both variants have an offer, the larger size offer must also be greater
        if curr["offer"] is not None and prev["offer"] is not None:
            if curr["offer"] <= prev["offer"]:
                errors.append(
                    f"{curr['size']} offer (₹{curr['offer']:.0f}) must be greater than "
                    f"{prev['size']} offer (₹{prev['offer']:.0f})."
                )

        # Edge case: larger size has no offer but smaller size does — fine, no rule broken.
        # Edge case: larger size has an offer but smaller doesn't — the offer must still
        # be > the smaller size's regular price to keep pricing sensible.
        if curr["offer"] is not None and prev["offer"] is None:
            if curr["offer"] <= prev["price"]:
                errors.append(
                    f"{curr['size']} offer (₹{curr['offer']:.0f}) must be greater than "
                    f"{prev['size']} regular price (₹{prev['price']:.0f})."
                )

    return errors

@staff_member_required(login_url="admin_login")
def add_product(request):
    if request.method == "POST":
        # ── Core fields ──────────────────────────────────────────────────────
        name = request.POST.get("name", "").strip()
        brand_input = request.POST.get("brand_name", "").strip()
        description = request.POST.get("description", "").strip()
        top_notes = request.POST.get("top_notes", "").strip()
        heart_notes = request.POST.get("heart_notes", "").strip()
        base_notes = request.POST.get("base_notes", "").strip()
        is_featured = "is_featured" in request.POST
        category_ids = request.POST.getlist("category")

        sizes = request.POST.getlist("v_size[]")
        prices = request.POST.getlist("v_price[]")
        offers = request.POST.getlist("v_offer[]")
        stocks = request.POST.getlist("v_stock[]")

        # ── Basic field validation ────────────────────────────────────────────
        form_errors = []

        if not name:
            form_errors.append("Product name is required.")
        elif Product.objects.filter(name__iexact=name).exists():
            form_errors.append(f"A product named '{name}' already exists.")

        if not brand_input:
            form_errors.append("Brand / House is required.")

        if not description:
            form_errors.append("Scent narrative (description) is required.")

        # ── Variant validation ────────────────────────────────────────────────
        variant_errors = _validate_variants_server(sizes, prices, offers)
        form_errors.extend(variant_errors)

        if not any(s.strip() for s in sizes):
            form_errors.append("At least one product variant is required.")

        # ── Server-side minimum image count check ─────────────────────────────
        images_data_check = request.POST.getlist("cropped_images[]")
        valid_image_count = sum(
            1 for img in images_data_check if img and img.strip() and ";base64," in img
        )
        if valid_image_count < 4:
            form_errors.append("Minimum 4 product images are required.")

        if form_errors:
            for err in form_errors:
                messages.error(request, err)
            return render(
                request,
                "products/admin_add_product.html",
                {
                    "brands": Brand.objects.all(),
                    "categories": Category.objects.filter(is_active=True),
                    "post": request.POST,  # pass back for re-filling the form
                },
            )

        # ── Create Brand & Product ────────────────────────────────────────────
        brand_obj = _get_or_create_brand(brand_input)

        product = Product.objects.create(
            name=name,
            brand=brand_obj,
            description=description,
            top_notes=top_notes,
            heart_notes=heart_notes,
            base_notes=base_notes,
            is_featured=is_featured,
        )

        if category_ids:
            product.categories.set(category_ids)

        # ── Create Variants ───────────────────────────────────────────────────
        SIZE_ORDER = {"8ml": 8, "20ml": 20, "50ml": 50, "100ml": 100}
        variant_data = []
        seen = set()
        for i in range(len(sizes)):
            size = sizes[i].strip() if sizes[i] else ""
            price_raw = prices[i].strip() if prices[i] else ""
            if not size or not price_raw or size in seen:
                continue
            seen.add(size)
            variant_data.append(
                {
                    "size": size,
                    "order": SIZE_ORDER.get(size, 999),
                    "price": float(price_raw),
                    "offer": (
                        float(offers[i])
                        if i < len(offers)
                        and offers[i].strip()
                        and float(offers[i]) > 0
                        else None
                    ),
                    "stock": (
                        int(stocks[i]) if i < len(stocks) and stocks[i].strip() else 0
                    ),
                }
            )

        variant_data.sort(key=lambda v: v["order"])
        for v in variant_data:
            ProductVariant.objects.create(
                product=product,
                size=v["size"],
                price=v["price"],
                offer_price=v["offer"],
                stock=v["stock"],
            )

        # ── Save Images ───────────────────────────────────────────────────────
        images_data = request.POST.getlist("cropped_images[]")
        for i, img_data in enumerate(images_data):
            if img_data and ";base64," in img_data:
                fmt, imgstr = img_data.split(";base64,")
                ext = fmt.split("/")[-1]
                image_file = ContentFile(
                    base64.b64decode(imgstr),
                    name=f"{slugify(product.name)}_{uuid.uuid4().hex[:4]}.{ext}",
                )
                ProductImage.objects.create(
                    product=product, image=image_file, is_main=(i == 0)
                )

        messages.success(request, f"'{product.name}' added to Scentora Registry.")
        return redirect("admin_product_list")

    return render(
        request,
        "products/admin_add_product.html",
        {
            "brands": Brand.objects.all(),
            "categories": Category.objects.filter(is_active=True),
        },
    )

@staff_member_required(login_url="admin_login")
def edit_product(request, product_id):
    product = get_object_or_404(Product, pk=product_id)

    if request.method == "POST":
        # ── Core fields (read first, validate before mutating `product`) ──────
        name = request.POST.get("name", "").strip()
        brand_input = request.POST.get("brand_name", "").strip()
        description = request.POST.get("description", "").strip()

        sizes = request.POST.getlist("v_size[]")
        prices = request.POST.getlist("v_price[]")
        offers = request.POST.getlist("v_offer[]")
        stocks = request.POST.getlist("v_stock[]")
        stocks_original = request.POST.getlist("v_stock_original[]")
        variant_ids = request.POST.getlist("variant_id[]")

        # ── Basic field validation ────────────────────────────────────────────
        form_errors = []

        if not name:
            form_errors.append("Product name is required.")
        elif Product.objects.filter(name__iexact=name).exclude(pk=product.pk).exists():
            form_errors.append(f"A product named '{name}' already exists.")

        if not brand_input:
            form_errors.append("Brand / House is required.")

        if not description:
            form_errors.append("Scent narrative (description) is required.")

        # ── Variant validation ────────────────────────────────────────────────
        variant_errors = _validate_variants_server(sizes, prices, offers)
        form_errors.extend(variant_errors)

        # ── Server-side minimum image count check ─────────────────────────────
        images_data_check = request.POST.getlist("cropped_images[]")
        valid_image_count = sum(
            1
            for img in images_data_check
            if img and img.strip() and img.strip() != "REMOVED"
        )
        if valid_image_count < 4:
            form_errors.append("Minimum 4 product images are required.")

        if form_errors:
            for err in form_errors:
                messages.error(request, err)
            return redirect("edit_product", product_id=product.id)

        # ── Brand ─────────────────────────────────────────────────────────────
        if brand_input:
            product.brand = _get_or_create_brand(
                brand_input
            )  # FIX: was broken get_or_create

        # ── Core fields ───────────────────────────────────────────────────────
        product.name = name
        product.description = description
        product.top_notes = request.POST.get("top_notes", product.top_notes)
        product.heart_notes = request.POST.get("heart_notes", product.heart_notes)
        product.base_notes = request.POST.get("base_notes", product.base_notes)
        product.is_featured = "is_featured" in request.POST

        product.save()

        # ── Category ──────────────────────────────────────────────────────────
        cat_id = request.POST.get("category")
        if cat_id and str(cat_id).isdigit():
            try:
                product.categories.set([Category.objects.get(id=int(cat_id))])
            except Category.DoesNotExist:
                pass

        # ── Variants ──────────────────────────────────────────────────────────
        existing_variant_ids = []

        for i in range(len(sizes)):
            size = sizes[i].strip() if sizes[i] else ""
            if not size:
                continue

            price = float(prices[i]) if prices[i] else 0
            offer_raw_val = offers[i] if i < len(offers) else ""
            offer = (
                float(offer_raw_val)
                if offer_raw_val and float(offer_raw_val) > 0
                else None
            )
            stock_raw = stocks[i] if i < len(stocks) and stocks[i] else ""
            stock = int(stock_raw) if stock_raw.strip().isdigit() else 0
            variant_id = variant_ids[i] if i < len(variant_ids) else ""

            if variant_id:
                try:
                    variant = ProductVariant.objects.get(id=variant_id, product=product)
                    variant.size = size
                    variant.price = price
                    variant.offer_price = offer

                    submitted_stock = stock
                    original_stock = (
                        int(stocks_original[i])
                        if i < len(stocks_original) and stocks_original[i]
                        else 0
                    )
                    if submitted_stock != original_stock:
                        variant.stock = submitted_stock

                    variant.save()
                    existing_variant_ids.append(variant.id)
                except ProductVariant.DoesNotExist:
                    pass
            else:
                variant = ProductVariant.objects.create(
                    product=product,
                    size=size,
                    price=price,
                    offer_price=offer,
                    stock=stock,
                )
                existing_variant_ids.append(variant.id)

        # Delete removed variants
        product.variants.exclude(id__in=existing_variant_ids).delete()

        # ── Images ────────────────────────────────────────────────────────────
        images_data = request.POST.getlist("cropped_images[]")
        existing_ids = request.POST.getlist("existing_image_ids[]")

        for i, img_id in enumerate(existing_ids):
            if i < len(images_data):
                img_status = images_data[i]
                if img_id and img_id.isdigit():
                    try:
                        img_obj = ProductImage.objects.get(
                            id=int(img_id), product=product
                        )
                        if img_status == "REMOVED":
                            if img_obj.image:
                                img_obj.image.delete(save=False)
                            img_obj.delete()
                        elif img_status and img_status.startswith("data:image"):
                            fmt, imgstr = img_status.split(";base64,")
                            ext = fmt.split("/")[-1]
                            if img_obj.image:
                                img_obj.image.delete(save=False)
                            img_obj.image = ContentFile(
                                base64.b64decode(imgstr),
                                name=f"{product.slug}_{uuid.uuid4().hex[:4]}.{ext}",
                            )
                            img_obj.save()
                    except ProductImage.DoesNotExist:
                        continue

        for i in range(len(existing_ids), len(images_data)):
            new_img_data = images_data[i]
            if new_img_data and new_img_data.startswith("data:image"):
                try:
                    fmt, imgstr = new_img_data.split(";base64,")
                    ext = fmt.split("/")[-1]
                    ProductImage.objects.create(
                        product=product,
                        image=ContentFile(
                            base64.b64decode(imgstr),
                            name=f"{product.slug}_{uuid.uuid4().hex[:4]}.{ext}",
                        ),
                    )
                except Exception as e:
                    print(f"Error creating new image: {e}")

        messages.success(
            request, f"Registry Updated: '{product.name}' has been updated."
        )
        return redirect("admin_product_list")

    return render(
        request,
        "products/admin_edit_product.html",
        {
            "product": product,
            "brands": Brand.objects.all(),
            "categories": Category.objects.filter(is_active=True),
        },
    )


@staff_member_required(login_url="admin_login")
@never_cache
def admin_archive(request):
    """
    Single page showing all unlisted (is_active=False) products and categories.
    Tab is controlled by ?tab=products (default) or ?tab=categories.
    Each tab has its own independent filters.
    """
    active_tab = request.GET.get("tab", "products")

    # ── ARCHIVED PRODUCTS ────────────────────────────────────────────────────
    products_list = (
        Product.objects.filter(is_active=False)
        .select_related("brand")
        .prefetch_related("categories", "variants", "images")
        .order_by("-created_at")
    )

    p_search = request.GET.get("p_search", "")
    p_brand = request.GET.get("p_brand", "all")
    p_cat = request.GET.get("p_cat", "all")

    if p_search:
        products_list = products_list.filter(
            Q(name__icontains=p_search) | Q(brand__name__icontains=p_search)
        )
    if p_brand != "all":
        products_list = products_list.filter(brand_id=p_brand)
    if p_cat != "all":
        products_list = products_list.filter(categories__id=p_cat)

    products_list = products_list.distinct()

    product_paginator = Paginator(products_list, 6)
    archived_products = product_paginator.get_page(request.GET.get("p_page"))

    # ── ARCHIVED CATEGORIES ──────────────────────────────────────────────────
    categories_list = Category.objects.filter(is_active=False).order_by("-created_at")

    c_search = request.GET.get("c_search", "")
    if c_search:
        categories_list = categories_list.filter(Q(name__istartswith=c_search))

    cat_paginator = Paginator(categories_list, 6)
    archived_categories = cat_paginator.get_page(request.GET.get("c_page"))

    # ── Counts ───────────────────────────────────────────────────────────────
    total_archived_products = Product.objects.filter(is_active=False).count()
    total_archived_categories = Category.objects.filter(is_active=False).count()

    brands = Brand.objects.all().order_by("name")
    categories = Category.objects.filter(is_active=True).order_by("name")

    return render(
        request,
        "products/admin_archive.html",
        {
            "active_tab": active_tab,
            "archived_products": archived_products,
            "p_search": p_search,
            "p_brand": p_brand,
            "p_cat": p_cat,
            "archived_categories": archived_categories,
            "c_search": c_search,
            "total_archived_products": total_archived_products,
            "total_archived_categories": total_archived_categories,
            "brands": brands,
            "categories": categories,
        },
    )


@staff_member_required(login_url="admin_login")
def toggle_product_status(request, product_id):
    product = get_object_or_404(Product, id=product_id)

    if not product.is_active:
        # Trying to UNARCHIVE — block if any of its categories are archived
        archived_categories = product.categories.filter(is_active=False)
        if archived_categories.exists():
            names = ", ".join(c.name for c in archived_categories)
            messages.error(
                request,
                f"Cannot unarchive '{product.name}': its category '{names}' is archived. "
                f"Unarchive the category first.",
            )
            referer = request.META.get("HTTP_REFERER", "")
            if "archive" in referer:
                return redirect("/products/admin/archive/?tab=products")
            return redirect("admin_product_list")

    product.is_active = not product.is_active
    product.save()
    status = "listed" if product.is_active else "unlisted (soft-deleted)"
    messages.success(request, f"Product '{product.name}' status set to {status}.")
    referer = request.META.get("HTTP_REFERER", "")
    if "archive" in referer:
        return redirect("/products/admin/archive/?tab=products")
    return redirect("admin_product_list")
