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
    path('users/', views.user_management, name='user_management'),
    path('users/confirm-block/<int:user_id>/', views.confirm_block_user, name='confirm_block_user'),
    path('users/toggle/<int:user_id>/', views.toggle_user_status, name='toggle_block'),
]
