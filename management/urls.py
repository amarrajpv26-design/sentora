from django.urls import path
from . import views

app_name = 'management'

urlpatterns = [
    # Orders Deck
    path('orders/', views.admin_orders_list, name='admin_orders_list'),
    path('orders/<str:order_id>/', views.admin_order_detail, name='admin_order_detail'),
    path('orders/<str:order_id>/status-update/', views.change_order_status, name='change_order_status'),

    # Inventory Deck
    path('inventory/', views.admin_inventory_list, name='admin_inventory_list'),
    path('inventory/<int:variant_id>/update-stock/', views.update_variant_stock, name='update_variant_stock'),
]