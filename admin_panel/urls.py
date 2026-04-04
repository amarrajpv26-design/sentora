from django.urls import path
from . import views

urlpatterns = [
    path("", views.admin_login, name="admin_login"),
    path("dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("users/", views.user_management, name="user_management"),
    path(
        "user/toggle/<int:user_id>/",
        views.toggle_user_status,
        name="toggle_user_status",
    ),
    path("logout/", views.admin_logout, name="admin_logout"),
    path('forgot-password/', views.forgot_password, name='forgot_password') ,
]
