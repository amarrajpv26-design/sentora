from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from orders.models import Order
from orders.views import record_status_change


class Command(BaseCommand):
    help = (
        "Auto-cancels ONLINE orders that never completed payment and were "
        "never retried, since no stock was ever reserved for them — they "
        "just need their order record closed out. Covers two cases: "
        "(1) payment_status=PENDING — checkout was abandoned mid-flow, "
        "no success/failure callback ever fired. "
        "(2) payment_status=FAILED — payment was declined/cancelled and "
        "the user never retried."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            help="Cancel eligible orders older than this many hours (default: 24)",
        )

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=options["hours"])

        expired_orders = Order.objects.filter(
            payment_method="ONLINE",
            payment_status__in=["PENDING", "FAILED"],
            order_status="PENDING",
            created_at__lt=cutoff,
        )

        count = 0
        for order in expired_orders:
            was_pending = order.payment_status == "PENDING"

            order.order_status = "CANCELLED"
            order.payment_status = "FAILED"
            order.cancellation_reason = (
                "Auto-cancelled: payment was never completed."
                if was_pending
                else "Auto-cancelled: payment failed and was never retried."
            )
            order.save()
            record_status_change(
                order, "CANCELLED", note="Auto-cancelled after payment timeout"
            )
            count += 1

        self.stdout.write(
            self.style.SUCCESS(f"Auto-cancelled {count} expired order(s).")
        )