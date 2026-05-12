from django.urls import path
from . import views

urlpatterns = [
    path("admin/categories/", views.admin_category_list, name="admin_category_list"),
    path("admin/categories/add/", views.add_category, name="add_category"),
    path(
        "admin/categories/edit/<int:category_id>/",
        views.edit_category,
        name="edit_category",
    ),
    path(
        "admin/categories/toggle/<int:category_id>/",
        views.toggle_category_status,
        name="toggle_category_status",
    ),
    path("admin/products/", views.admin_product_list, name="admin_product_list"),
    path(
        "admin/products/detail/<int:product_id>/",
        views.product_detail,
        name="admin_product_detail",
    ),
    path("admin/products/add/", views.add_product, name="add_product"),
    path(
        "admin/products/edit/<int:product_id>/", views.edit_product, name="edit_product"
    ),
    path(
        "admin/products/toggle/<int:product_id>/",
        views.toggle_product_status,
        name="toggle_product_status",
    ),
]
