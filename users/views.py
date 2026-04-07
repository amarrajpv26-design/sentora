from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from .models import User
from .utils import generate_otp, send_otp_email
from django.utils import timezone


def home(request):
    return render(request, "users/index.html")


def welcome_view(request):
    return render(request, "users/welcome.html")


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
            return redirect("dashboard")
        else:
            messages.error(request, "Invalid credentials.")
    return render(request, "users/login.html")


def user_logout(request):
    logout(request)
    return redirect("home")


def user_signup(request):
    if request.method == "POST":
        email = request.POST.get("email")
        username = request.POST.get("username")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "users/signup.html")

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
            return render(request, "users/signup.html")

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken.")
            return render(request, "users/signup.html")

        user = User.objects.create_user(
            username=username, email=email, password=password
        )
        user.is_active = False

        otp = generate_otp()
        user.otp_code = otp
        user.otp_created_at = timezone.now()
        user.save()

        try:
            send_otp_email(email, otp)
            request.session["verification_email"] = email
            messages.success(
                request, "A verification code has been sent to your email."
            )
            return redirect("verify_otp")
        except Exception as e:
            messages.error(request, "Failed to send email. Please try again.")
            return render(request, "users/signup.html")

    return render(request, "users/signup.html")


def verify_otp(request):
    email = request.session.get("verification_email")
    user=User.objects.get(email=email)

    if not email:
        return redirect("user_signup")

    if request.method == "POST":
        entered_otp = request.POST.get("otp")

        if user.is_otp_expired():
            messages.error(request, "OTP has expired. Please request a new one.")
        elif user.otp_code == entered_otp:
            user.is_active = True
            user.is_verified = True
            user.otp_code = None
            user.save()
            messages.success(request, "Account verified! Welcome to Scentora.")
            return redirect("user_login")
        else:
            messages.error(request, "Invalid OTP code.")

    return render(request, "users/verify_otp.html", {"email": email})


def clear_otp(self):
    self.otp_code = None
    self.otp_created_at = None
    self.save()


def resend_otp(request):
    email = request.session.get("verification_email")
    if email:
        user = User.objects.get(email=email)
        otp = generate_otp()
        user.otp_code = otp
        user.otp_created_at = timezone.now()
        user.save()
        send_otp_email(email, otp)
        messages.success(request, "A new OTP has been sent to your email.")
    return redirect("verify_otp")
