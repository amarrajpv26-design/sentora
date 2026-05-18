from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.cache import never_cache
from .models import User, Address
from django.contrib.auth.decorators import login_required
from .utils import generate_otp, send_otp_email
from django.utils import timezone
from django.db import IntegrityError
from .forms import UserEditForm
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from .forms import UserProfileForm, AddressForm
import random
from django.core.mail import send_mail
from django.conf import settings
from datetime import date,timedelta


@never_cache
def welcome_view(request):
    return render(request, "users/welcome.html")

@login_required(login_url='welcome')
@never_cache
def home(request):
    if not request.user.is_authenticated:
        return redirect("welcome")
    
    return render(request, "users/index.html")


@never_cache
def user_signup(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        context = {"typed_username": username, "typed_email": email}

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "users/signup.html", context)

        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already taken.")
            return render(request, "users/signup.html", context)

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered.")
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


@never_cache
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


@never_cache
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


@never_cache
def user_login(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")

        try:
            user_obj = User.objects.filter(email=email).first()

            if user_obj:
                if not user_obj.is_active or getattr(user_obj, "is_blocked", False):
                    messages.error(request, "This account has been restricted.")
                    return redirect("user_login")

        except Exception as e:
            pass

        user = authenticate(request, username=email, password=password)

        if user is not None:
            login(request, user)
            return redirect("home")
        else:
            messages.error(request, "Invalid credentials.")
            return redirect("user_login")

    return render(request, "users/login.html")


@never_cache
def user_logout(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect("welcome")


@never_cache
@login_required
def logout_confirmation_view(request):
    return render(request, "users/logout_confirm.html")


@never_cache
@login_required
def profile_view(request):
    return render(
        request,
        "users/profile.html",
        {
            "user": request.user,
            "active_tab": "personal_info",
        },
    )


@never_cache
@login_required
def edit_profile_view(request):
    user = request.user

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        phone_number = request.POST.get("phone_number", "").strip()
        new_email = request.POST.get("email", "").strip()
        dob = request.POST.get('dob') # Get DOB here
        profile_image = request.FILES.get("profile_image")

        errors = False

        processed_dob = user.dob
        # --- VALIDATION ---
        if not username:
            messages.error(request, "Username is required.", extra_tags="username")
            errors = True
        elif User.objects.filter(username=username).exclude(pk=user.pk).exists():
            messages.error(request, f"The identity '{username}' is already claimed.", extra_tags="username")
            errors = True

        if phone_number and (not phone_number.isdigit() or len(phone_number) != 10):
            messages.error(request, "Phone number must be exactly 10 digits.", extra_tags="phone")
            errors = True

        # DOB Logic (Cleaned up)
        valid_dob = None
        if dob:
            try:
                selected_date = date.fromisoformat(dob)
                today = date.today()
        
        # Calculate age
                age = today.year - selected_date.year - ((today.month, today.day) < (selected_date.month, selected_date.day))
        
                if selected_date > today:
                    messages.error(request, "Invalid Date: Future dates are not permitted.")
                    errors = True
                elif age < 15:
                    messages.error(request, "Identity rejected: Minimum age requirement is 15 years.")
                    errors = True
                else:
                    processed_dob = selected_date
            
            except ValueError:
                messages.error(request, "Invalid date format.")
                errors = True
        else:
            # If the user clears the date, we allow it to be None
            processed_dob = None

        if new_email and new_email != user.email:
            if User.objects.filter(email=new_email).exists():
                messages.error(request, "This email is already linked.", extra_tags="email")
                errors = True

        if errors:
            return render(request, "users/edit_profile.html", {"user": user})

        # --- PROCESSING ---
        # If email changed, save everything to session and redirect to OTP
        if new_email and new_email != user.email:
            request.session["pending_profile_update"] = {
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "phone_number": phone_number,
                "dob": dob, # Save DOB to session too!
            }
            return redirect("change_email_request")

        # Standard Update
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.phone_number = phone_number
        user.dob = processed_dob
        
        if profile_image:
            user.profile_image = profile_image

        user.save()
        messages.success(request, "VAULT UPDATED: YOUR IDENTITY HAS BEEN REFINED.")
        return redirect("profile")

    return render(request, "users/edit_profile.html", {"user": user})


@never_cache
@login_required
def password_change_view(request):
    if request.method == "POST":
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, "Your password was successfully updated!")
            return redirect("profile")
        else:
            messages.error(request, "Please correct the error below.")
    else:
        form = PasswordChangeForm(request.user)
    return render(request, "users/change_password.html", {"form": form})


@never_cache
@login_required
def add_address_view(request):
    if request.method == "POST":
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            messages.success(request, "New address added to your vault.")
            return redirect("profile")
    else:
        form = AddressForm()
    return render(request, "users/add_address.html", {"form": form})


@never_cache
@login_required
def edit_address_view(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)

    if request.method == "POST":
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            form.save()
            messages.success(request, "Address updated in your vault.")
            return redirect("profile")
    else:
        form = AddressForm(instance=address)

    return render(request, "users/add_address.html", {"form": form, "edit_mode": True})


@never_cache
@login_required
def delete_address_view(request, pk):
    if request.method == "POST":
        address = get_object_or_404(Address, pk=pk, user=request.user)
        address.delete()
        messages.success(request, "Destination removed from archive.")
    return redirect("profile")


@never_cache
@login_required
def change_email_request_view(request):
    otp = str(random.randint(100000, 999999))

    request.session["email_change_otp"] = otp
    request.session.modified = True

    try:
        send_mail(
            "Scentora Vault: Email Change",
            f"Verification Code: {otp}",
            settings.EMAIL_HOST_USER,
            [request.user.email],
            fail_silently=False,
        )
        messages.success(request, f"CODE SENT TO {request.user.email}")
    except Exception as e:
        messages.error(request, f"MAIL ERROR: {str(e)}")
        return redirect("profile")

    return redirect("verify_email_otp")


@never_cache
@login_required
def verify_email_change(request):
    saved_otp = request.session.get("email_change_otp")

    if not saved_otp:
        messages.error(request, "SECURITY ERROR: INITIAL OTP NOT FOUND.")
        return redirect("profile")

    if request.method == "POST":
        user_otp = request.POST.get("otp")
        if user_otp == saved_otp:
            request.session["email_otp_verified"] = True
            request.session.save()
            request.session.modified = True
            return redirect("final_email_update_view")
        else:
            messages.error(request, "INVALID CODE.")

    return render(request, "users/verify_email_otp.html")


@never_cache
def final_email_update_view(request):
    if not request.session.get("email_otp_verified"):
        messages.error(request, "PLEASE VERIFY YOUR IDENTITY FIRST.")
        return redirect("profile")

    if request.method == "POST":
        new_email = request.POST.get("new_email")

        new_otp = str(random.randint(100000, 999999))
        request.session["pending_new_email"] = new_email
        request.session["new_email_otp"] = new_otp

        send_mail(
            "Scentora Vault: Verify New Email",
            f"Your code for the new email is: {new_otp}",
            settings.EMAIL_HOST_USER,
            [new_email],
        )

        request.session.save()
        return redirect("verify_new_email")

    return render(request, "users/final_email_update.html")


@never_cache
@login_required
def verify_new_email_otp(request):
    new_email = request.session.get("pending_new_email")
    correct_otp = request.session.get("new_email_otp")

    if not new_email or not correct_otp:
        messages.error(request, "SESSION EXPIRED. PLEASE START THE PROCESS AGAIN.")
        return redirect("profile")

    if request.method == "POST":
        entered_otp = request.POST.get("otp")

        if entered_otp == correct_otp:
            user = request.user
            user.email = new_email
            user.save()

            temp_keys = [
                "email_otp_verified",
                "pending_new_email",
                "new_email_otp",
                "email_change_otp",
            ]
            for key in temp_keys:
                if key in request.session:
                    del request.session[key]

            messages.success(request, "IDENTITY UPDATED: YOUR NEW EMAIL IS NOW ACTIVE.")
            return redirect("profile")
        else:
            messages.error(request, "INVALID VERIFICATION CODE.")

    return render(request, "users/verify_new_email.html", {"email": new_email})
