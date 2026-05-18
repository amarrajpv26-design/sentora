from django.urls import path
from . import views

app_name = "shop" 

urlpatterns = [
    path('', views.product_list, name='product_list'),
    path('product/<int:product_id>/', views.product_detail, name='product_detail'),
    path("brands/", views.brand_list, name="brand_list"),
    path("categories/", views.category_list, name="category_list"),
]