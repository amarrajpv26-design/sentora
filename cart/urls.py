# cart/urls.py
from django.urls import path
from . import views

app_name = 'cart'

urlpatterns = [
    path('', views.cart_detail, name='cart_detail'),
    path('add/<int:variant_id>/', views.cart_add, name='cart_add'),
    path('update/<int:variant_id>/', views.cart_update, name='cart_update'),
    path('cart-count/', views.cart_count_only, name='cart_count_only'),
    path('remove/<int:variant_id>/', views.cart_remove, name='cart_remove'),
    path("wishlist/toggle/<int:variant_id>/", views.wishlist_toggle, name="wishlist_toggle"),
    path("wishlist/", views.wishlist_detail, name="wishlist_detail"),
    path('wishlist/count/', views.wishlist_count_only, name='wishlist_count_only'),
    path("wishlist/remove/<int:variant_id>/", views.wishlist_remove, name="wishlist_remove"),
]