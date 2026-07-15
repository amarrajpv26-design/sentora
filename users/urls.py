from django.urls import path
from django.contrib.auth import views as auth_views
from .forms import ScentoraPasswordResetForm, ScentoraSetPasswordForm
from . import views

urlpatterns = [
    path("", views.welcome_view, name="welcome"),
    path("home/", views.home, name="home"),
    path("signup/", views.user_signup, name="user_signup"),
    path("verify-otp/", views.verify_otp, name="verify_otp"),
    path("resend-otp/", views.resend_otp, name="resend_otp"),
    path("login/", views.user_login, name="user_login"),
    path("logout/", views.user_logout, name="user_logout"),
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            form_class=ScentoraPasswordResetForm,
            template_name="users/password_reset_form.html",
            email_template_name="email/password_reset_email.html",
            subject_template_name="email/password_reset_subject.txt",
            html_email_template_name="email/password_reset_email.html",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="users/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="users/password_reset_confirm.html",
            form_class=ScentoraSetPasswordForm,
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset-complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="users/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path(
        "profile/logout-confirmation/",
        views.logout_confirmation_view,
        name="logout_confirmation",
    ),
    path("profile/", views.profile_view, name="profile"),
    path("profile/password/", views.password_change_view, name="password_change"),
    path("profile/address/add/", views.add_address_view, name="add_address"),
    path(
        "profile/address/edit/<int:pk>/", views.edit_address_view, name="edit_address"
    ),
    path(
        "profile/address/delete/<int:pk>/",
        views.delete_address_view,
        name="delete_address",
    ),
    path("profile/edit/", views.edit_profile_view, name="edit_profile"),
    path(
        "profile/email/change/",
        views.change_email_request_view,
        name="change_email_request",
    ),
    path(
        "profile/email/verify-otp/", views.verify_email_change, name="verify_email_otp"
    ),
    path(
        "profile/email/update/",
        views.final_email_update_view,
        name="final_email_update_view",
    ),
    path(
        "profile/email/verify-new/", views.verify_new_email_otp, name="verify_new_email"
    ),
    path("search/", views.search_products, name="search_products"),
    path("our-story/", views.our_story, name="our_story"),
    path("philosophy/", views.philosophy, name="philosophy"),
    path("boutiques/", views.boutiques, name="boutiques"),
    path("contact/", views.contact, name="contact"),
    path("shipping-policy/", views.shipping_policy, name="shipping_policy"),
    path(
        "return-refund-policy/", views.return_refund_policy, name="return_refund_policy"
    ),
    path("privacy-policy/", views.privacy_policy, name="privacy_policy"),
    path("terms-conditions/", views.terms_conditions, name="terms_conditions"),
    path("about-scentora/", views.about_scentora, name="about_scentora"),
    path("404-test/", views.custom_404, name="404-test"),
]
