from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from users.views import custom_404

handler404 = "users.views.custom_404"

urlpatterns = [
    path("admin-control/", include("admin_panel.urls")),
    path("", include("users.urls")),
    path("products/", include("products.urls")),
    path("shop/", include("shop.urls")),
    path("accounts/", include("allauth.urls")),
    path("cart/", include("cart.urls")),
    path("checkout/", include("checkout.urls")),
    path("orders/", include("orders.urls")),
    path("management/", include("management.urls", namespace="management")),
    path("wallet/", include("wallets.urls")),
    path("reviews/", include("reviews.urls", namespace="reviews")),
    path("offers/", include("offers.urls", namespace="offers")),
    path("coupons/", include("coupons.urls", namespace="coupons")),
]

# Only static files needed — Cloudinary handles media now
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
