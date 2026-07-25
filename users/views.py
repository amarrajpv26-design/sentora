import re
import random
from datetime import date
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.cache import never_cache
from .models import User, Address
from django.db.models import Q
from django.contrib.auth.decorators import login_required
from .utils import (
    generate_otp,
    send_otp_email,
    OTP_TTL_MINUTES,
    is_otp_expired,
    get_resend_wait_seconds,
)
from django.utils import timezone
from django.db import IntegrityError
from .forms import UserEditForm
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from .forms import UserProfileForm, AddressForm
from django.core.mail import send_mail
from django.conf import settings
from wallets.models import Wallet
from products.models import Product, Category, ProductImage, Brand
from django.template.loader import render_to_string

# Server-side username rule (mirrors the JS check in signup.html):
# 3-20 chars, must start with a letter, only letters/numbers/underscore after that.
USERNAME_REGEX = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]{2,19}$")


@never_cache
def welcome_view(request):

    hero_categories = Category.objects.filter(
        is_active=True, category_image__isnull=False
    )

    featured_products = Product.objects.filter(
        is_active=True, is_featured=True
    ).prefetch_related("images", "variants")

    categories = Category.objects.filter(is_active=True, is_featured=True).order_by(
        "id"
    )

    brands = Brand.objects.filter(is_active=True).order_by("id")[:6]

    return render(
        request,
        "users/welcome.html",
        {
            "hero_categories": hero_categories,
            "featured_products": featured_products,
            "categories": categories,
            "brands": brands,
        },
    )


@login_required(login_url="welcome")
@never_cache
def home(request):
    hero_categories = Category.objects.filter(
        is_active=True, category_image__isnull=False
    )

    featured_products = Product.objects.filter(
        is_active=True, is_featured=True
    ).prefetch_related("images", "variants")

    categories = Category.objects.filter(is_active=True, is_featured=True).order_by(
        "id"
    )
    brands = Brand.objects.filter(is_active=True).order_by("id")[:6]

    context = {
        "hero_categories": hero_categories,
        "featured_products": featured_products,
        "categories": categories,
        "brands": brands,
        # 'private_reserve' and 'limited_edition' are now handled globally!
    }

    return render(request, "users/index.html", context)


@never_cache
def user_signup(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "GET":
        ref = request.GET.get("ref")
        if ref:
            request.session["referral_code_input"] = ref

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email")
        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")
        referral_input = (
            request.POST.get("referral_code", "").strip()
            or request.session.get("referral_code_input", "")
            or request.session.get("referral_token", "")
        )

        context = {"typed_username": username, "typed_email": email}

        if not USERNAME_REGEX.match(username):
            messages.error(
                request,
                "Username must be 3-20 characters, start with a letter, and contain "
                "only letters, numbers, and underscores.",
            )
            return render(request, "users/signup.html", context)

        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return render(request, "users/signup.html", context)

        # Password strength validation
        if len(password) < 8:
            messages.error(
                request, "Security requirement: Password must be at least 8 characters."
            )
            return render(request, "users/signup.html", context)
        if not re.search(r"[A-Z]", password):
            messages.error(
                request,
                "Security requirement: Password must contain at least one uppercase letter.",
            )
            return render(request, "users/signup.html", context)
        if not re.search(r"[0-9]", password):
            messages.error(
                request,
                "Security requirement: Password must contain at least one number.",
            )
            return render(request, "users/signup.html", context)
        if not re.search(r'[()[\]{}|\\`~!@#$%^&*_\-+=;:\'",<>./?]', password):
            messages.error(
                request,
                "Security requirement: Password must contain at least one special character.",
            )
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
                "referral_input": referral_input,
            }
            return redirect("verify_otp")
        except Exception as e:
            messages.error(request, f"Email delivery failed: {e}")
            return render(request, "users/signup.html", context)

    return render(
        request,
        "users/signup.html",
        {"referral_code_prefill": request.session.get("referral_code_input", "")},
    )


@never_cache
def verify_otp(request):
    signup_data = request.session.get("pending_signup")
    if not signup_data:
        messages.error(request, "Session expired. Please sign up again.")
        return redirect("user_signup")

    otp_created_at = signup_data["otp_created_at"]

    if request.method == "POST":
        entered_otp = request.POST.get("otp")

        if is_otp_expired(otp_created_at):
            messages.error(request, "This code has expired. Please request a new one.")
            return render(
                request,
                "users/verify_otp.html",
                {
                    "email": signup_data["email"],
                    "resend_wait_seconds": get_resend_wait_seconds(otp_created_at),
                },
            )

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

            referral_input = signup_data.get("referral_input")
            if referral_input:
                from offers.utils import apply_referral_to_new_user

                apply_referral_to_new_user(user, referral_input)

            for key in ["pending_signup", "referral_code_input", "referral_token"]:
                if key in request.session:
                    del request.session[key]

            messages.success(request, "Verification successful! Welcome to Secntora.")
            return redirect("user_login")
        else:
            messages.error(request, "Invalid code. Please try again.")

    return render(
        request,
        "users/verify_otp.html",
        {
            "email": signup_data["email"],
            "resend_wait_seconds": get_resend_wait_seconds(otp_created_at),
        },
    )


@never_cache
def resend_otp(request):
    signup_data = request.session.get("pending_signup")

    if not signup_data:
        messages.error(request, "Identification lost. Please sign up again.")
        return redirect("user_signup")

    try:
        new_otp = generate_otp()

        signup_data["otp"] = new_otp
        signup_data["otp_created_at"] = str(
            timezone.now()
        )  # reset TTL + resend cooldown
        request.session["pending_signup"] = signup_data

        send_otp_email(signup_data["email"], new_otp)

        messages.success(request, "A fresh verification code has been dispatched.")
    except Exception as e:
        messages.error(request, "Failed to resend email. Please try again.")

    return redirect("verify_otp")


@never_cache
def user_login(request):
    if request.user.is_authenticated:
        return redirect("home")

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


@login_required
@never_cache
def profile_view(request):

    wallet, created = Wallet.objects.get_or_create(user=request.user)

    return render(
        request,
        "users/profile.html",
        {
            "user": request.user,
            "wallet": wallet,
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
        dob = request.POST.get("dob")  # Get DOB here
        profile_image = request.FILES.get("profile_image")

        errors = False

        processed_dob = user.dob
        # --- VALIDATION ---
        if not username:
            messages.error(request, "Username is required.", extra_tags="username")
            errors = True

        elif User.objects.filter(username=username).exclude(pk=user.pk).exists():
            messages.error(
                request,
                f"The identity '{username}' is already claimed.",
                extra_tags="username",
            )
            errors = True

        if phone_number and (not phone_number.isdigit() or len(phone_number) != 10):
            messages.error(
                request, "Phone number must be exactly 10 digits.", extra_tags="phone"
            )
            errors = True

        # DOB Logic (Cleaned up)
        valid_dob = None
        if dob:
            try:
                selected_date = date.fromisoformat(dob)
                today = date.today()

                # Calculate age
                age = (
                    today.year
                    - selected_date.year
                    - (
                        (today.month, today.day)
                        < (selected_date.month, selected_date.day)
                    )
                )

                if selected_date > today:
                    messages.error(
                        request, "Invalid Date: Future dates are not permitted."
                    )
                    errors = True
                elif age < 15:
                    messages.error(
                        request,
                        "Identity rejected: Minimum age requirement is 15 years.",
                    )
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
                messages.error(
                    request, "This email is already linked.", extra_tags="email"
                )
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
                "dob": dob,  # Save DOB to session too!
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
            new_password = request.POST.get("new_password1")
            if request.user.check_password(new_password):
                messages.error(
                    request,
                    "Security requirement: New password cannot be the same as your current password.",
                )
                return render(request, "users/change_password.html", {"form": form})
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
    has_addresses = Address.objects.filter(user=request.user).exists()

    if request.method == "POST":
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user

            # First address is always the default, regardless of the checkbox
            if not has_addresses:
                address.is_default = True

            # Only one address can be default at a time — unset any existing one
            if address.is_default:
                Address.objects.filter(user=request.user).update(is_default=False)

            address.save()
            messages.success(request, "New address added to your vault.")
            next_url = request.POST.get("next")
            if next_url:
                return redirect(next_url)

            return redirect("profile")
    else:
        form = AddressForm()

    return render(
        request,
        "users/add_address.html",
        {
            "form": form,
            "has_addresses": has_addresses,
        },
    )


@never_cache
@login_required
def edit_address_view(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)

    # If this address is currently the default, it cannot be un-defaulted
    # from this view — the only way to change the default is to create/edit
    # a DIFFERENT address and mark that one as default instead. The template
    # uses this flag to hide the checkbox and show an explanatory note.
    is_locked_default = address.is_default

    if request.method == "POST":
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            updated_address = form.save(commit=False)

            # Enforce the lock server-side too: no matter what was submitted
            # (e.g. a manually crafted request), a currently-default address
            # stays default through this view.
            if is_locked_default:
                updated_address.is_default = True

            # Only one address can be default at a time — unset any other one
            if updated_address.is_default:
                Address.objects.filter(user=request.user).exclude(pk=address.pk).update(
                    is_default=False
                )

            updated_address.save()
            messages.success(request, "Address updated in your vault.")
            next_url = request.POST.get("next")

            if next_url:
                return redirect(next_url)

            return redirect("profile")
    else:
        form = AddressForm(instance=address)

    return render(
        request,
        "users/add_address.html",
        {
            "form": form,
            "edit_mode": True,
            "is_locked_default": is_locked_default,
        },
    )


@never_cache
@login_required
def delete_address_view(request, pk):
    if request.method == "POST":
        address = get_object_or_404(Address, pk=pk, user=request.user)
        was_default = address.is_default
        address.delete()

        # If the deleted address was the default, promote the most recently
        # created remaining address to default so the user is never left
        # without one (as long as at least one address still exists).
        if was_default:
            next_default = (
                Address.objects.filter(user=request.user)
                .order_by("-created_at")
                .first()
            )
            if next_default:
                next_default.is_default = True
                next_default.save(update_fields=["is_default"])

        messages.success(request, "Destination removed from archive.")
    return redirect("profile")


@never_cache
@login_required
def change_email_request_view(request):
    otp = str(random.randint(100000, 999999))

    request.session["email_change_otp"] = otp
    request.session["email_change_otp_created_at"] = str(timezone.now())
    request.session.modified = True

    try:
        html_message = render_to_string(
            "email/email_change_otp.html", {"otp": otp, "ttl_minutes": OTP_TTL_MINUTES}
        )
        send_mail(
            "Scentora Vault: Email Change Verification",
            f"Your verification code is: {otp}",
            settings.EMAIL_HOST_USER,
            [request.user.email],
            fail_silently=False,
            html_message=html_message,
        )

        messages.success(request, f"CODE SENT TO {request.user.email}")
    except Exception as e:
        messages.error(request, f"MAIL ERROR: {str(e)}")
        return redirect("profile")

    return redirect("verify_email_otp")


@never_cache
@login_required
def resend_email_change_otp(request):
    if "email_change_otp" not in request.session:
        messages.error(request, "Session expired. Please try again.")
        return redirect("profile")

    otp = str(random.randint(100000, 999999))
    request.session["email_change_otp"] = otp
    request.session["email_change_otp_created_at"] = str(timezone.now())
    request.session.modified = True

    try:
        html_message = render_to_string(
            "email/email_change_otp.html", {"otp": otp, "ttl_minutes": OTP_TTL_MINUTES}
        )
        send_mail(
            "Scentora Vault: Email Change Verification",
            f"Your verification code is: {otp}",
            settings.EMAIL_HOST_USER,
            [request.user.email],
            fail_silently=False,
            html_message=html_message,
        )
        messages.success(request, "A fresh verification code has been dispatched.")
    except Exception as e:
        messages.error(request, f"MAIL ERROR: {str(e)}")

    return redirect("verify_email_otp")


@never_cache
@login_required
def verify_email_change(request):
    saved_otp = request.session.get("email_change_otp")
    otp_created_at = request.session.get("email_change_otp_created_at")

    if not saved_otp or not otp_created_at:
        messages.error(request, "SECURITY ERROR: INITIAL OTP NOT FOUND.")
        return redirect("profile")

    if request.method == "POST":
        if is_otp_expired(otp_created_at):
            messages.error(request, "This code has expired. Please request a new one.")
            return render(
                request,
                "users/verify_email_otp.html",
                {
                    "resend_wait_seconds": get_resend_wait_seconds(otp_created_at),
                },
            )

        user_otp = request.POST.get("otp")
        if user_otp == saved_otp:
            request.session["email_otp_verified"] = True
            request.session.save()
            request.session.modified = True
            return redirect("final_email_update_view")
        else:
            messages.error(request, "INVALID CODE.")

    return render(
        request,
        "users/verify_email_otp.html",
        {
            "resend_wait_seconds": get_resend_wait_seconds(otp_created_at),
        },
    )


@never_cache
def final_email_update_view(request):
    if not request.session.get("email_otp_verified"):
        messages.error(request, "PLEASE VERIFY YOUR IDENTITY FIRST.")
        return redirect("profile")

    if request.method == "POST":
        new_email = request.POST.get("new_email", "").strip().lower()

        # Check if email already exists
        if User.objects.filter(email__iexact=new_email).exists():
            messages.error(request, "This email is already linked to another account.")
            return render(request, "users/final_email_update.html")

        # Check if same as current email
        if new_email == request.user.email.lower():
            messages.error(
                request, "New email cannot be the same as your current email."
            )
            return render(request, "users/final_email_update.html")

        new_otp = str(random.randint(100000, 999999))
        request.session["pending_new_email"] = new_email
        request.session["new_email_otp"] = new_otp
        request.session["new_email_otp_created_at"] = str(timezone.now())

        html_message = render_to_string(
            "email/new_email_otp.html", {"otp": new_otp, "ttl_minutes": OTP_TTL_MINUTES}
        )
        send_mail(
            "Scentora Vault: Verify New Email",
            f"Your confirmation code is: {new_otp}",
            settings.EMAIL_HOST_USER,
            [new_email],
            html_message=html_message,
        )

        request.session.save()
        return redirect("verify_new_email")

    return render(request, "users/final_email_update.html")


@never_cache
@login_required
def resend_new_email_otp(request):
    new_email = request.session.get("pending_new_email")
    if not new_email:
        messages.error(request, "Session expired. Please try again.")
        return redirect("profile")

    new_otp = str(random.randint(100000, 999999))
    request.session["new_email_otp"] = new_otp
    request.session["new_email_otp_created_at"] = str(timezone.now())
    request.session.modified = True

    try:
        html_message = render_to_string(
            "email/new_email_otp.html", {"otp": new_otp, "ttl_minutes": OTP_TTL_MINUTES}
        )
        send_mail(
            "Scentora Vault: Verify New Email",
            f"Your confirmation code is: {new_otp}",
            settings.EMAIL_HOST_USER,
            [new_email],
            html_message=html_message,
        )
        messages.success(request, "A fresh verification code has been dispatched.")
    except Exception as e:
        messages.error(request, f"MAIL ERROR: {str(e)}")

    return redirect("verify_new_email")


@never_cache
@login_required
def verify_new_email_otp(request):
    new_email = request.session.get("pending_new_email")
    correct_otp = request.session.get("new_email_otp")
    otp_created_at = request.session.get("new_email_otp_created_at")

    if not new_email or not correct_otp or not otp_created_at:
        messages.error(request, "SESSION EXPIRED. PLEASE START THE PROCESS AGAIN.")
        return redirect("profile")

    if request.method == "POST":
        if is_otp_expired(otp_created_at):
            messages.error(request, "This code has expired. Please request a new one.")
            return render(
                request,
                "users/verify_new_email.html",
                {
                    "email": new_email,
                    "resend_wait_seconds": get_resend_wait_seconds(otp_created_at),
                },
            )

        entered_otp = request.POST.get("otp")

        if entered_otp == correct_otp:
            try:
                user = request.user
                user.email = new_email
                user.save()

                temp_keys = [
                    "email_otp_verified",
                    "pending_new_email",
                    "new_email_otp",
                    "new_email_otp_created_at",
                    "email_change_otp",
                    "email_change_otp_created_at",
                ]
                for key in temp_keys:
                    if key in request.session:
                        del request.session[key]

                messages.success(
                    request, "IDENTITY UPDATED: YOUR NEW EMAIL IS NOW ACTIVE."
                )
                return redirect("profile")
            except Exception:
                messages.error(
                    request,
                    "Something went wrong updating your email. Please try again.",
                )
        else:
            messages.error(request, "INVALID VERIFICATION CODE.")

    return render(
        request,
        "users/verify_new_email.html",
        {
            "email": new_email,
            "resend_wait_seconds": get_resend_wait_seconds(otp_created_at),
        },
    )


def search_products(request):

    query = request.GET.get("q", "").strip()

    products = Product.objects.none()

    if query:

        products = (
            Product.objects.filter(
                Q(name__icontains=query)
                | Q(description__icontains=query)
                | Q(top_notes__icontains=query)
                | Q(heart_notes__icontains=query)
                | Q(base_notes__icontains=query)
                | Q(brand__name__icontains=query)
                | Q(categories__name__icontains=query)
            )
            .filter(is_active=True)
            .distinct()
        )

    return render(
        request,
        "users/search_results.html",
        {
            "query": query,
            "products": products,
        },
    )


def our_story(request):
    return render(request, "pages/our_story.html")


def philosophy(request):
    return render(request, "pages/philosophy.html")


def boutiques(request):
    return render(request, "pages/boutiques.html")


def contact(request):
    return render(request, "pages/contact.html")


def shipping_policy(request):
    return render(request, "pages/shipping_policy.html")


def return_refund_policy(request):
    return render(request, "pages/return_refund_policy.html")


def privacy_policy(request):
    return render(request, "pages/privacy_policy.html")


def terms_conditions(request):
    return render(request, "pages/terms_conditions.html")


def about_scentora(request):
    return render(request, "pages/about_scentora.html")


from django.urls import reverse


def custom_404(request, exception=None):
    is_admin = request.path.startswith("/admin-control/")
    context = {
        "return_url": reverse("admin_dashboard") if is_admin else reverse("home"),
        "return_label": "Return to Dashboard" if is_admin else "Return Home",
        "is_admin": is_admin,
    }
    return render(request, "404.html", context, status=404)


def custom_500(request):
    is_admin = request.path.startswith("/admin-control/")
    context = {
        "return_url": reverse("admin_dashboard") if is_admin else reverse("home"),
        "return_label": "Return to Dashboard" if is_admin else "Return Home",
        "is_admin": is_admin,
    }
    return render(request, "500.html", context, status=500)


def custom_403(request, exception=None):
    is_admin = request.path.startswith("/admin-control/")
    context = {
        "return_url": reverse("admin_dashboard") if is_admin else reverse("home"),
        "return_label": "Return to Dashboard" if is_admin else "Return Home",
        "is_admin": is_admin,
    }
    return render(request, "403.html", context, status=403)
