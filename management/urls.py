from django.urls import path
from . import views

app_name = "management"

urlpatterns = [
    path("orders/", views.admin_orders_list, name="admin_orders_list"),
    path("orders/<str:order_id>/", views.admin_order_detail, name="admin_order_detail"),
    path(
        "orders/<str:order_id>/status-update/",
        views.change_order_status,
        name="change_order_status",
    ),
    path(
        "order-item/<int:item_id>/status/",
        views.handle_item_status_change,
        name="handle_item_status_change",
    ),
    path("inventory/", views.admin_inventory_list, name="admin_inventory_list"),
    path(
        "inventory/<int:variant_id>/update-stock/",
        views.update_variant_stock,
        name="update_variant_stock",
    ),
    path(
        "order-item/<int:item_id>/approve-return/",
        views.approve_return_item,
        name="approve_return_item",
    ),
    path(
        "order-item/<int:item_id>/reject-return/",
        views.reject_return_item,
        name="reject_return_item",
    ),
    path(
        "orders/<str:order_id>/approve-return/",
        views.approve_full_return,
        name="approve_full_return",
    ),
    path(
        "orders/<str:order_id>/reject-return/",
        views.reject_full_return,
        name="reject_full_return",
    ),
    path(
        "returns/",
        views.admin_return_requests,
        name="admin_return_requests",
    ),
    path(
        "returns/<int:item_id>/",
        views.admin_return_request_detail,
        name="admin_return_request_detail",
    ),
    path(
        "transactions/", views.admin_transactions_list, name="admin_transactions_list"
    ),
    path(
        "transactions/<int:pk>/",
        views.admin_transaction_detail,
        name="admin_transaction_detail",
    ),
    path(
        "sales-report/",
        views.sales_report,
        name="sales_report",
    ),
    path(
        "sales-report/pdf/",
        views.sales_report_pdf,
        name="sales_report_pdf",
    ),
]
