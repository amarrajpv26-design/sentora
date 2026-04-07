from django.urls import path
from . import views

urlpatterns = [
    path("", views.welcome_view, name="welcome"),
    path("home/", views.home, name="home"),
    path("signup/", views.user_signup, name="user_signup"),
    path("verify-otp/", views.verify_otp, name="verify_otp"),
    path("resend-otp/", views.resend_otp, name="resend_otp"),
    path("login/", views.user_login, name="user_login"),
    path("logout/", views.user_logout, name="user_logout"),
    # path("forgot-password/", views.forgot_password, name="forgot_password"),
    # path("profile/", views.user_profile, name="user_profile"),
    # path("profile/edit/", views.edit_profile, name="edit_profile"),
    # path("profile/change-password/", views.change_password, name="change_password"),
    # path("profile/addresses/", views.address_management, name="address_management"),
    # path("profile/addresses/add/", views.add_address, name="add_address"),
    # path(
    #     "profile/addresses/delete/<int:address_id>/",
    #     views.delete_address,
    #     name="delete_address",
    # ),
]
