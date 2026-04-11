from django.shortcuts import render, redirect
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from .models import User
from .utils import generate_otp, send_otp_email
from django.utils import timezone
from django.db import IntegrityError


def home(request):
    return render(request, "users/index.html")


def welcome_view(request):
    return render(request, "users/welcome.html")


def user_signup(request):
    if request.method == "POST":
        email = request.POST.get("email")
        username = request.POST.get("username")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        context = {"typed_username": username, "typed_email": email}

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "users/signup.html", context)

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
            return render(request, "users/signup.html", context)

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken.")
            return render(request, "users/signup.html", context)

        otp = generate_otp()

        try:
            send_otp_email(email, otp)
            request.session["pending_signup"] = {
                "username": username,
                "email": email,
                "password": password,
                "otp": otp,
                "otp_created_at": str(timezone.now()),
            }
            return redirect("verify_otp")
        except Exception as e:
            messages.error(request, f"Email delivery failed: {e}")
            return render(request, "users/signup.html", context)

    return render(request, "users/signup.html")


def verify_otp(request):
    signup_data = request.session.get("pending_signup")
    if not signup_data:
        messages.error(request, "Session expired. Please sign up again.")
        return redirect("user_signup")

    if request.method == "POST":
        entered_otp = request.POST.get("otp")

        if signup_data["otp"] == entered_otp:
            try:
                user = User.objects.create_user(
                    username=signup_data["username"],
                    email=signup_data["email"],
                    password=signup_data["password"],
                )
                user.is_active = True
                user.save()

            except IntegrityError:
                user = User.objects.get(email=signup_data["email"])
                user.is_active = True
                user.save()

            if "pending_signup" in request.session:
                del request.session["pending_signup"]

            messages.success(request, "Verification successful! Welcome to Secntora.")
            return redirect("user_login")
        else:
            messages.error(request, "Invalid code. Please try again.")

    return render(request, "users/verify_otp.html", {"email": signup_data["email"]})


def clear_otp(self):
    self.otp_code = None
    self.otp_created_at = None
    self.save()


def resend_otp(request):
    signup_data = request.session.get("pending_signup")

    if not signup_data:
        messages.error(request, "Identification lost. Please sign up again.")
        return redirect("user_signup")

    try:
        
        new_otp = generate_otp()

        signup_data["otp"] = new_otp
        request.session["pending_signup"] = signup_data

        send_otp_email(signup_data["email"], new_otp)

        messages.success(request, "A fresh verification code has been dispatched.")
    except Exception as e:
        messages.error(request, "Failed to resend email. Please try again.")

    return redirect("verify_otp")


def user_login(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        user = authenticate(request, username=email, password=password)

        if user is not None:
            if user.is_blocked:
                messages.error(request, "This account has been restricted")
                return render(request, "login.html")

            login(request, user)
            return redirect("home")
        else:
            messages.error(request, "Invalid credentials.")
            return redirect("user_login")

    return render(request, "users/login.html")


def user_logout(request):
    logout(request)
    return redirect("home")
