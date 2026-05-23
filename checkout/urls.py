from django.urls import path
from . import views

urlpatterns = [

    # Cart checkout
    path(
        '',
        views.checkout_view,
        name='checkout'
    ),

    # Buy now checkout
    path(
        'buy-now/<int:variant_id>/',
        views.buy_now_checkout_view,
        name='buy_now_checkout'
    ),

    # Place order
    path(
        'place-order/',
        views.place_order_view,
        name='place_order'
    ),

    # Success page
    path(
        'success/<str:order_id>/',
        views.order_success_view,
        name='order_success'
    ),
]