from django.urls import path
from . import views

urlpatterns = [

    
    path(
        '',
        views.checkout_view,
        name='checkout'
    ),


    path(
        'buy-now/<int:variant_id>/',
        views.buy_now_checkout_view,
        name='buy_now_checkout'
    ),

    
    path(
        'place-order/',
        views.place_order_view,
        name='place_order'
    ),

    
    path(
        'success/<str:order_id>/',
        views.order_success_view,
        name='order_success'
    ),
]