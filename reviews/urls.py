from django.urls import path
from . import views

app_name = "reviews"

urlpatterns = [
    # User
    path("submit/<int:product_id>/", views.submit_review, name="submit_review"),

    # Admin
    path("admin/reviews/", views.admin_review_list, name="admin_review_list"),
    path(
        "admin/reviews/<int:review_id>/",
        views.admin_review_detail,
        name="admin_review_detail",
    ),
    path(
        "admin/reviews/<int:review_id>/approve/",
        views.approve_review,
        name="approve_review",
    ),
    path(
        "admin/reviews/<int:review_id>/unapprove/",
        views.unapprove_review,
        name="unapprove_review",
    ),
    path(
        "admin/reviews/<int:review_id>/delete/",
        views.delete_review,
        name="delete_review",
    ),
    path(
        "admin/reviews/bulk-action/",
        views.bulk_review_action,
        name="bulk_review_action",
    ),
]