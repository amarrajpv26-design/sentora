from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.auth.decorators import user_passes_test
from django.contrib.admin.views.decorators import staff_member_required

User = get_user_model()


def is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@user_passes_test(is_admin, login_url="admin_login")
def admin_dashboard(request):
    return render(request, "admin_panel/dashboard.html")


def admin_login(request):

    if request.user.is_authenticated and request.user.is_staff:
        return redirect("admin_dashboard")

    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        remember_me = request.POST.get("remember_me")

        user = authenticate(request, email=email, password=password)

        if user is not None and user.is_staff:
            login(request, user)
            if remember_me:
                request.session.set_expiry(1209600)
            else:
                request.session.set_expiry(0)

            return redirect("admin_dashboard")
        else:
            messages.error(request, "Invalid credentials or not authorized.")
    return render(request, "admin_panel/login.html")


def admin_logout(request):
    logout(request)
    return redirect("admin_login")


def forgot_password(request):
    return render(request, "admin_panel/forgot_password.html")


@staff_member_required
def user_management(request):
    users = User.objects.filter(is_superuser=False).order_by("-date_joined")
    search_query = request.GET.get("search", "") or ""
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

    active_count = User.objects.filter(is_active=True, is_superuser=False).count()
    blocked_count = User.objects.filter(is_active=False, is_superuser=False).count()
    total_count = users.count()

    paginator = Paginator(users, 10)
    page_number = request.GET.get("page")
    users = paginator.get_page(page_number)

    context = {
        "users": users,
        "active_count": active_count,
        "blocked_count": blocked_count,
        "total_count": total_count,
        "search_query": search_query,
        "status_filter": status_filter,
    }

    return render(request, "admin_panel/user_management.html", context)


@staff_member_required
def toggle_user_status(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    target_user.is_active = not target_user.is_active
    target_user.save()
    return redirect("user_management")


def block_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.is_active = False
    user.save()
    messages.success(request, f"User {user.username} has been blocked.")
    return redirect("user_management")


def unblock_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.is_active = True
    user.save()
    messages.success(request, f"User {user.username} has been unblocked.")
    return redirect("user_management")


@staff_member_required
def user_detail(request, user_id):
    customer = get_object_or_404(User, id=user_id)

    orders = customer.orders.all().order_by("-created_at")[:5]
    addresses = customer.addresses.all()
    total_spent = sum(
        order.total_price for order in customer.orders.filter(status="Delivered")
    )
    context = {
        "customer": customer,
        "orders": orders,
        "addresses": addresses,
        "total_spent": total_spent,
    }

    return render(request, "admin_panel/user_detail.html", context)


@staff_member_required
def save_admin_note(request, user_id):
    if request.method == "POST":
        customer = get_object_or_404(User, id=user_id)
        note_text = request.POST.get("note_content", "").strip()
        note, created = AdminNote.objects.get_or_create(user=customer)
        note.content = note_text
        note.save()

        messages.sucesss(request, "Note saved sucessfully")
        return redirect("user_detail", user_id=user_id)
    return redirect("user_management")
