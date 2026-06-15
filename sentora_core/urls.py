"""
URL configuration for sentora_core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

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
    path("offers/", include("offers.urls",namespace="offers")),
    path("coupons/", include("coupons.urls", namespace="coupons")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
