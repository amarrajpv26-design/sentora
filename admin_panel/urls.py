from django.urls import path
from django.contrib import admin
from . import views

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("", views.admin_login, name="admin_login"),
    path("dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("users/", views.user_management, name="user_management"),
    path(
        "user/toggle/<int:user_id>/",
        views.toggle_user_status,
        name="toggle_user_status",
    ),
    path("logout/", views.admin_logout, name="admin_logout"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("users/block/<int:user_id>/", views.block_user, name="block_user"),
    path("users/unblock/<int:user_id>/", views.unblock_user, name="unblock_user"),
]
