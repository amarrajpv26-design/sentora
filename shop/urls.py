from django.urls import path
from . import views

app_name = "shop" 

urlpatterns = [
    path('', views.product_list, name='product_list'),
    path('product/<uuid:product_uuid>/', views.product_detail, name='product_detail'),
    path("brands/", views.brand_list, name="brand_list"),
    path("categories/", views.category_list, name="category_list"),
    path(
        "category/<slug:slug>/",
        views.category_products,
        name="category_products"
    ),
]