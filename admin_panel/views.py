from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib.auth.decorators import user_passes_test

User = get_user_model()


def is_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@user_passes_test(is_admin, login_url="admin_login")
def admin_dashboard(request):
    return render(request, "admin_panel/dashboard.html")


def admin_login(request):

    if request.user.is_authenticated and request.user.is_staff:
        return redirect('admin_dashboard')
    
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


def user_management(request):
    user_list = User.objects.filter(is_superuser=False).order_by("-date_joined")
    query = request.GET.get("search")
    if query:
        user_list = user_list.filter(
            Q(user_name__icontains=query) | Q(email__icontains == query)
        )

    paginator = Paginator(user_list, 10)
    page_number = request.GET.get("page")
    users = paginator.get_page(page_number)

    return render(
        request, "admin_panel/user_management.html", {"users": users, "query": query}
    )


def toggle_user_status(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.is_active = not user.is_active
    user.save()
    return redirect("user_management")
