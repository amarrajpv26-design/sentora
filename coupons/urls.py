from django.urls import path

from . import views

app_name = "coupons"

urlpatterns = [
    path("admin/", views.admin_coupon_list, name="admin_coupon_list"),
    path("admin/create/", views.admin_coupon_create, name="admin_coupon_create"),
    path("admin/<int:pk>/edit/", views.admin_coupon_edit, name="admin_coupon_edit"),
    path("admin/<int:pk>/delete/", views.admin_coupon_delete, name="admin_coupon_delete"),
]