from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Review
from products.models import Product
from orders.models import OrderItem
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q, Avg

from .models import Review


@login_required
def submit_review(request, product_id):
    
    product = get_object_or_404(Product, id=product_id)

    if request.method != 'POST':
        return redirect('shop:product_detail', product_uuid=product.uuid)

    # Find a delivered order item for this product by this user
    delivered_item = OrderItem.objects.filter(
        order__user=request.user,
        product_variant__product=product,
        item_status='ACTIVE',
        order__order_status__in=['DELIVERED', 'RETURN_REJECTED'],
    ).exclude(review__isnull=False).first()

    if not delivered_item:
        messages.error(request, "You can only review products you have purchased and received.")
        return redirect('shop:product_detail', product_uuid=product.uuid)

    rating = request.POST.get('rating', '').strip()
    title = request.POST.get('title', '').strip()
    comment = request.POST.get('comment', '').strip()

    if not rating or not comment:
        messages.error(request, "Rating and comment are required.")
        return redirect('shop:product_detail', product_uuid=product.uuid)

    Review.objects.create(
        product=product,
        user=request.user,
        order_item=delivered_item,
        rating=int(rating),
        title=title,
        comment=comment,
        is_approved=False,
    )

    messages.success(request, "Review submitted. It will appear after approval.")
    return redirect('shop:product_detail', product_uuid=product.uuid)


@staff_member_required
def admin_review_list(request):
    reviews = Review.objects.select_related(
        "product",
        "user",
        "order_item",
    ).all()

    search = request.GET.get("search", "").strip()

    if search:
        reviews = reviews.filter(
            Q(product__name__icontains=search)
            | Q(user__username__icontains=search)
            | Q(title__icontains=search)
        )

    status = request.GET.get("status")

    if status == "approved":
        reviews = reviews.filter(is_approved=True)

    elif status == "pending":
        reviews = reviews.filter(is_approved=False)

    rating = request.GET.get("rating")

    if rating and rating.isdigit():
        reviews = reviews.filter(rating=int(rating))

    total_reviews = Review.objects.count()

    approved_reviews = Review.objects.filter(
        is_approved=True
    ).count()

    pending_reviews = Review.objects.filter(
        is_approved=False
    ).count()

    average_rating = (
        Review.objects.aggregate(avg=Avg("rating"))["avg"]
        or 0
    )

    paginator = Paginator(reviews, 15)

    page_number = request.GET.get("page")

    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "search": search,
        "status": status,
        "rating": rating,
        "total_reviews": total_reviews,
        "approved_reviews": approved_reviews,
        "pending_reviews": pending_reviews,
        "average_rating": round(average_rating, 1),
    }

    return render(
        request,
        "reviews/admin_review_list.html",
        context,
    )

@staff_member_required
def admin_review_detail(request, review_id):
    review = get_object_or_404(
        Review.objects.select_related(
            "product",
            "user",
            "order_item",
            "order_item__order",
        ).prefetch_related(
            "product__images"
        ),
        id=review_id,
    )

    context = {
        "review": review,
    }

    return render(
        request,
        "reviews/admin_review_detail.html",
        context,
    )


@staff_member_required
def approve_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)

    review.is_approved = True
    review.save(update_fields=["is_approved"])

    messages.success(request, "Review approved successfully.")
    return redirect("reviews:admin_review_detail", review_id=review.id)


@staff_member_required
def unapprove_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)

    review.is_approved = False
    review.save(update_fields=["is_approved"])

    messages.success(request, "Review hidden successfully.")
    return redirect("reviews:admin_review_detail", review_id=review.id)


@staff_member_required
def delete_review(request, review_id):
    review = get_object_or_404(Review, id=review_id)

    review.delete()

    messages.success(request, "Review deleted successfully.")
    return redirect("reviews:admin_review_list")

@staff_member_required
def bulk_review_action(request):
    if request.method != "POST":
        return redirect("reviews:admin_review_list")

    action = request.POST.get("action")
    review_ids = request.POST.getlist("review_ids")

    if not review_ids:
        messages.warning(request, "No reviews selected.")
        return redirect("reviews:admin_review_list")

    reviews = Review.objects.filter(id__in=review_ids)

    if action == "approve":
        updated = reviews.update(is_approved=True)

        messages.success(
            request,
            f"{updated} review(s) approved successfully."
        )

    elif action == "unapprove":
        updated = reviews.update(is_approved=False)

        messages.success(
            request,
            f"{updated} review(s) hidden successfully."
        )

    elif action == "delete":
        count = reviews.count()

        reviews.delete()

        messages.success(
            request,
            f"{count} review(s) deleted successfully."
        )

    else:
        messages.error(request, "Invalid action selected.")

    return redirect("reviews:admin_review_list")