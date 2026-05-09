from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.cache import never_cache
from .models import Category,Product, Brand, ProductVariant, ProductImage
from .forms import CategoryForm
import base64
from django.utils.text import slugify
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
import uuid


@staff_member_required
@never_cache
def admin_category_list(request):
    # Requirement a.iv: Sort in descending order
    categories_list = Category.objects.all().order_by("-created_at")

    active_count = Category.objects.filter(is_active=True).count()
    featured_count = Category.objects.filter(is_featured=True).count()
    archived_count = Category.objects.filter(is_active=False).count()

    # Requirement a.ii: Search Logic
    search_query = request.GET.get("search", "")
    status_filter = request.GET.get('status', 'all')

    if search_query:
        categories_list = categories_list.filter(
           Q(name__istartswith=search_query)
        )
    if status_filter == 'active':
        categories_list = categories_list.filter(is_active=True)
    elif status_filter == 'archived':
        categories_list = categories_list.filter(is_active=False)


    # Requirement a.iii: Pagination (Backend)
    paginator = Paginator(categories_list, 5)  # 10 categories per page
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


@staff_member_required
def add_category(request):
    if request.method == "POST":
        form = CategoryForm(request.POST, request.FILES)
        cropped_data = request.POST.get("cropped_image")

        if form.is_valid():
            category = form.save(commit=False)

            # Normalize: 'men' or 'MEN' becomes 'Men'
            category.name = category.name.strip().capitalize()

            # Manual check for immediate feedback
            if Category.objects.filter(name=category.name).exists():
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
                # This triggers the model's full_clean() and iexact check
                category.save()
                messages.success(
                    request, f"Vault '{category.name}' established successfully."
                )
                return redirect("admin_category_list")
            except ValidationError as e:
                # Catching model-level validation errors (like the name__iexact check)
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


@staff_member_required
def edit_category(request, category_id):
    category = get_object_or_404(Category, pk=category_id)

    if request.method == "POST":
        form = CategoryForm(request.POST, request.FILES, instance=category)
        cropped_data = request.POST.get("cropped_image")

        if form.is_valid():
            updated_category = form.save(commit=False)

            # 1. Normalize for consistency
            updated_category.name = updated_category.name.strip().capitalize()

            # 2. Duplicate Check: Ensure we aren't renaming to another existing category name
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

            # 3. Handle Image
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

            # 4. Final Save with Model-level validation catch
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


@staff_member_required
def toggle_category_status(request, category_id):
    # Requirement a.i: Soft Delete (Unlist)
    category = get_object_or_404(Category, id=category_id)
    category.is_active = not category.is_active
    category.save()

    status = "activated" if category.is_active else "unlisted (soft-deleted)"
    messages.success(request, f"Category '{category.name}' has been {status}.")
    return redirect("admin_category_list")


@staff_member_required
@never_cache
def admin_product_list(request):
    # Fetch products with related brand and categories to avoid multiple DB hits
    products_list = Product.objects.all().select_related('brand').prefetch_related('categories', 'variants').order_by("-created_at")

    # Search and Filtering
    search_query = request.GET.get("search", "")
    brand_filter = request.GET.get("brand", "all")
    category_filter = request.GET.get("category", "all")
    
    if search_query:
        products_list = products_list.filter(Q(name__icontains=search_query) | Q(brand__name__icontains=search_query))
    
    if brand_filter != 'all':
        products_list = products_list.filter(brand_id=brand_filter)
    if category_filter != "all":
        products_list = products_list.filter(categories__id=category_filter)
    

    products_list = products_list.distinct()
    
    # Pagination
    
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
        },
    )


@staff_member_required
def product_detail(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    # Fetch variants and images related to this product
    variants = product.variants.all().order_by('price')
    gallery = product.images.all()
    
    context = {
        'product': product,
        'variants': variants,
        'gallery': gallery,
    }
    return render(request, "products/admin_product_detail.html", context)


@staff_member_required
def add_product(request):
    if request.method == "POST":
        # 1. Handle Brand Consistency (Silent Creation)
        brand_input = request.POST.get('brand_name', '').strip()
        brand_obj = None
        if brand_input:
            brand_obj, _ = Brand.objects.get_or_create(
                name__iexact=brand_input,
                defaults={'name': brand_input.title(), 'slug': slugify(brand_input)}
            )

        # 2. Create Product
        product = Product.objects.create(
            name=request.POST.get('name'),
            brand=brand_obj,
            description=request.POST.get('description'),
            top_notes=request.POST.get('top_notes'),
            heart_notes=request.POST.get('heart_notes'),
            base_notes=request.POST.get('base_notes'),
            is_featured='is_featured' in request.POST
        )
        
        category_ids = request.POST.getlist('category') # Matches HTML name="category"
        if category_ids:
            product.categories.set(category_ids)

        # 3. Handle Variants (Updated to match v_ names)
        sizes = request.POST.getlist('v_size[]')
        prices = request.POST.getlist('v_price[]')
        offers = request.POST.getlist('v_offer[]')
        stocks = request.POST.getlist('v_stock[]')
        
        for i in range(len(sizes)):
            if sizes[i] and prices[i]:
                ProductVariant.objects.create(
                    product=product,
                    size=sizes[i],
                    price=prices[i],
                    offer_price=offers[i] if offers[i] else None,
                    stock=stocks[i] if stocks[i] else 0
                )

        # 4. Images
        images_data = request.POST.getlist('cropped_images[]')
        for i, img_data in enumerate(images_data):
            if img_data and ";base64," in img_data:
                format, imgstr = img_data.split(";base64,")
                ext = format.split("/")[-1]
                image_file = ContentFile(base64.b64decode(imgstr), name=f"{slugify(product.name)}_{uuid.uuid4().hex[:4]}.{ext}")
                ProductImage.objects.create(product=product, image=image_file, is_main=(i==0))

        messages.success(request, f"'{product.name}' added to Scentora Registry.")
        return redirect('admin_product_list')

    return render(request, "products/admin_add_product.html", {
        "brands": Brand.objects.all(),
        "categories": Category.objects.all()
    })


@staff_member_required
def edit_product(request, product_id):
    product = get_object_or_404(Product, pk=product_id)

    if request.method == "POST":
        # 1. Update Brand Identity
        brand_input = request.POST.get('brand_name', '').strip()
        if brand_input:
            # get_or_create is cleaner and prevents race conditions
            brand_obj, _ = Brand.objects.get_or_create(
                name__iexact=brand_input,
                defaults={'name': brand_input.title(), 'slug': slugify(brand_input)}
            )
            product.brand = brand_obj

        # Update core text fields
        product.name = request.POST.get('name', product.name).strip()
        product.description = request.POST.get('description', product.description)
        product.top_notes = request.POST.get('top_notes', product.top_notes)
        product.heart_notes = request.POST.get('heart_notes', product.heart_notes)
        product.base_notes = request.POST.get('base_notes', product.base_notes)
        product.is_featured = 'is_featured' in request.POST
        
        # Save attributes to the Product table
        product.save()

        # --- CATEGORY LOGIC (ManyToMany) ---
        cat_id = request.POST.get('category')
        if cat_id and str(cat_id).isdigit():
            try:
                selected_category = Category.objects.get(id=int(cat_id))
                # .set() replaces all existing categories with this one
                product.categories.set([selected_category])
            except Category.DoesNotExist:
                pass

        # 2. Synchronize Variants
        product.variants.all().delete()
        sizes = request.POST.getlist('v_size[]')
        prices = request.POST.getlist('v_price[]')
        offers = request.POST.getlist('v_offer[]')
        stocks = request.POST.getlist('v_stock[]')

        for i in range(len(sizes)):
            if sizes[i].strip():
                ProductVariant.objects.create(
                    product=product,
                    size=sizes[i],
                    price=prices[i] if prices[i] and prices[i] != '' else 0,
                    offer_price=offers[i] if offers[i] and offers[i] != '' else None,
                    stock=stocks[i] if stocks[i] and stocks[i] != '' else 0
                )

        # 3. Synchronize Images
        images_data = request.POST.getlist('cropped_images[]')
        existing_ids = request.POST.getlist('existing_image_ids[]')

        # Handle Existing Images
        for i, img_id in enumerate(existing_ids):
            if i < len(images_data):
                img_status = images_data[i]
                if img_id and img_id.isdigit():
                    try:
                        img_obj = ProductImage.objects.get(id=int(img_id), product=product)
                        if img_status == "REMOVED":
                            if img_obj.image: img_obj.image.delete(save=False)
                            img_obj.delete()
                        elif img_status and img_status.startswith("data:image"):
                            format, imgstr = img_status.split(";base64,")
                            ext = format.split("/")[-1]
                            if img_obj.image: img_obj.image.delete(save=False)
                            img_obj.image = ContentFile(base64.b64decode(imgstr), name=f"{product.slug}_{uuid.uuid4().hex[:4]}.{ext}")
                            img_obj.save()
                    except ProductImage.DoesNotExist: continue

        # Handle New Images
        for i in range(len(existing_ids), len(images_data)):
            new_img_data = images_data[i]
            if new_img_data and new_img_data.startswith("data:image"):
                try:
                    format, imgstr = new_img_data.split(";base64,")
                    ext = format.split("/")[-1]
                    ProductImage.objects.create(
                        product=product,
                        image=ContentFile(base64.b64decode(imgstr), name=f"{product.slug}_{uuid.uuid4().hex[:4]}.{ext}")
                    )
                except Exception as e:
                    print(f"Error creating new image: {e}")

        messages.success(request, f"Registry Updated: {product.name} has been updated.")
        return redirect('admin_product_list')

    return render(request, "products/admin_edit_product.html", {
        "product": product,
        "brands": Brand.objects.all(),
        "categories": Category.objects.all(),
    })


@staff_member_required
def toggle_product_status(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product.is_active = not product.is_active
    product.save()

    status = "listed" if product.is_active else "unlisted (soft-deleted)"
    messages.success(request, f"Product '{product.name}' status set to {status}.")
    return redirect("admin_product_list")
