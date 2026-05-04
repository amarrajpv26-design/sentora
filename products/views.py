from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.cache import never_cache
from .models import Category
from .forms import CategoryForm
import base64
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError


@staff_member_required
@never_cache
def admin_category_list(request):
    # Requirement a.iv: Sort in descending order
    categories_list = Category.objects.all().order_by("created_at")

    active_count = Category.objects.filter(is_active=True).count()
    featured_count = Category.objects.filter(is_featured=True).count()
    archived_count = Category.objects.filter(is_active=False).count()

    # Requirement a.ii: Search Logic
    search_query = request.GET.get("search", "")
    if search_query:
        categories_list = categories_list.filter(
            Q(name__icontains=search_query) | Q(description__icontains=search_query)
        )

    # Requirement a.iii: Pagination (Backend)
    paginator = Paginator(categories_list, 3)  # 10 categories per page
    page_number = request.GET.get("page")
    categories = paginator.get_page(page_number)

    return render(
        request,
        "products/admin_category_list.html",
        {
            "categories": categories,
            "search_query": search_query,
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
