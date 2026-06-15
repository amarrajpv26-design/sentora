from django.urls import path
from . import views

app_name = "offers"

urlpatterns = [
    # Dashboard
    path("", views.offer_dashboard, name="dashboard"),

    # Product Offers
    path("product/create/", views.product_offer_create, name="product_offer_create"),
    path("product/<int:pk>/edit/", views.product_offer_edit, name="product_offer_edit"),
    path("product/<int:pk>/toggle/", views.product_offer_toggle, name="product_offer_toggle"),
    path("product/<int:pk>/delete/", views.product_offer_delete, name="product_offer_delete"),

    # Category Offers
    path("category/create/", views.category_offer_create, name="category_offer_create"),
    path("category/<int:pk>/edit/", views.category_offer_edit, name="category_offer_edit"),
    path("category/<int:pk>/toggle/", views.category_offer_toggle, name="category_offer_toggle"),
    path("category/<int:pk>/delete/", views.category_offer_delete, name="category_offer_delete"),

    # Referral Offers
    path("referral/create/", views.referral_offer_create, name="referral_offer_create"),
    path("referral/<int:pk>/edit/", views.referral_offer_edit, name="referral_offer_edit"),
    path("referral/<int:pk>/toggle/", views.referral_offer_toggle, name="referral_offer_toggle"),
    path("referral/<int:pk>/delete/", views.referral_offer_delete, name="referral_offer_delete"),
    path("referral/<int:pk>/detail/", views.referral_offer_detail, name="referral_offer_detail"),

    # Public: token URL signup
    path("ref/<uuid:token>/", views.referral_signup_redirect, name="referral_signup"),
]