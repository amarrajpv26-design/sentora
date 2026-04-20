from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.cache import never_cache
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.auth.decorators import user_passes_test
from django.contrib.admin.views.decorators import staff_member_required

User = get_user_model()



def is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@never_cache
@user_passes_test(is_admin, login_url="admin_login")
def admin_dashboard(request):
    return render(request, "admin_panel/dashboard.html")


@never_cache
def admin_login(request):

    if request.user.is_authenticated and request.user.is_staff:
        return redirect("admin_dashboard")

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, email=email, password=password)

        if user is not None and user.is_staff:
            login(request, user)

            return redirect("admin_dashboard")
        else:
            messages.error(request, "Invalid credentials or not authorized.")
    return render(request, "admin_panel/login.html")


@never_cache
def admin_logout(request):
    if request.method == "POST":
        logout(request)
        messages.success(request, "You have been logged out successfully.")
        return redirect("admin_login")

    return render(request, "admin_panel/confirm_logout.html")


@never_cache
@staff_member_required
def user_management(request):
    users = User.objects.filter(is_superuser=False).order_by("-date_joined")
    sort_order = request.GET.get("sort", "newest")
    search_query = request.GET.get("search", "")

    if search_query:
        users = users.filter(
            Q(username__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
        )
    status_filter = request.GET.get("status", "")
    if status_filter == "active":
        users = users.filter(is_active=True)
    elif status_filter == "blocked":
        users = users.filter(is_active=False)

    if sort_order == "oldest":
        users = users.order_by("date_joined")
    elif sort_order == "alpha":
        users = users.order_by("username")
    else:
        users = users.order_by("-date_joined")

    active_count = User.objects.filter(is_active=True, is_superuser=False).count()
    blocked_count = User.objects.filter(is_active=False, is_superuser=False).count()
    total_count = users.count()

    paginator = Paginator(users, 5)
    page_number = request.GET.get("page")
    users = paginator.get_page(page_number)

    context = {
        "users": users,
        "active_count": active_count,
        "blocked_count": blocked_count,
        "total_count": total_count,
        "search_query": search_query,
        "status_filter": status_filter,
        "sort_order": sort_order,
    }

    return render(request, "admin_panel/user_management.html", context)


@never_cache
@staff_member_required
def user_detail_view(request, user_id):
    customer = get_object_or_404(User, id=user_id)

    orders = customer.orders.all().order_by("-created_at")[:5]

    context = {
        "customer": customer,
        "orders": orders,
        "total_spent": sum(order.total_price for order in orders), 
    }

    return render(request, "admin_panel/user_detail.html", context)





@never_cache
@staff_member_required
def toggle_user_status(request, user_id):
    if request.method == "POST":
        user = get_object_or_404(User, id=user_id)

        if user.is_active:
            user.is_active = False
            action = "blocked"
        else:
            user.is_active = True
            action = "unblocked"

        user.save()
        messages.success(
            request, f"User {user.username} has been successfully {action}."
        )
        return redirect("user_management")

    return redirect("user_management")

@never_cache
def confirm_block_user(request, user_id):
    user_to_manage = get_object_or_404(User, id=user_id)

    return render(
        request, "admin_panel/confirm_block.html", {"user_to_manage": user_to_manage}
    )