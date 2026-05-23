from django.urls import path
from . import views

urlpatterns = [
    path("", views.order_list_view, name="order_list"),
    path("<str:order_id>/", views.order_detail_view, name="order_detail"),
    path("cancel/<str:order_id>/", views.cancel_order_view, name="cancel_order"),
    path(
        "cancel-item/<int:item_id>/",
        views.cancel_order_item_view,
        name="cancel_order_item",
    ),
    path("return/<str:order_id>/", views.return_order_view, name="return_order"),
    path(
        "invoice/<str:order_id>/", views.download_invoice_view, name="download_invoice"
    ),
]
