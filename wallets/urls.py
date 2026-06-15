from django.urls import path
from . import views

urlpatterns = [
    path("", views.wallet_view, name="wallet"),
    path("recharge/", views.wallet_recharge_view, name="wallet_recharge"),
    path("payment-success/", views.wallet_payment_success, name="wallet_payment_success"),
    path("create-order/", views.create_wallet_order, name="create_wallet_order"),
]