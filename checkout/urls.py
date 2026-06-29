from django.urls import path
from . import views

urlpatterns = [
    path("", views.checkout_view, name="checkout"),
    path(
        "buy-now/<int:variant_id>/",
        views.buy_now_checkout_view,
        name="buy_now_checkout",
    ),
    path("place-order/", views.place_order_view, name="place_order"),
    path("success/<str:order_id>/", views.order_success_view, name="order_success"),
    path(
        "payment/verify/", views.payment_verify_view, name="payment_verify"
    ),  # The "checker" for Razorpay
    path("payment/failed/", views.payment_failed_view, name="payment_failed"),
    path("retry/<str:order_id>/", views.retry_payment_view, name="retry_payment"),
    path("coupon/apply/", views.apply_coupon_view, name="apply_coupon"),
    path("coupon/remove/", views.remove_coupon_view, name="remove_coupon"),
    path(
        "coupon/available/", views.get_available_coupons, name="get_available_coupons"
    ),
]
