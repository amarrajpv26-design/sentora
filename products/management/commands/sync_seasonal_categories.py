"""
Management command: sync_seasonal_categories
Run daily via cron to activate/archive seasonal categories and their products.

Cron setup (runs every day at midnight):
    crontab -e
    0 0 * * * /path/to/venv/bin/python /path/to/sentora/manage.py sync_seasonal_categories

Replace paths with your actual venv and project paths, e.g.:
    0 0 * * * /home/amar/sentora/venv/bin/python /home/amar/sentora/manage.py sync_seasonal_categories
"""

from django.core.management.base import BaseCommand
from products.models import Category, Product


class Command(BaseCommand):
    help = (
        "Activate or archive seasonal categories based on today's date (runs annually)."
    )

    def handle(self, *args, **options):
        seasonal_categories = Category.objects.filter(is_seasonal=True)

        activated = 0
        archived = 0

        for category in seasonal_categories:
            in_season = category.is_in_season()

            # ── Activate ──────────────────────────────────────────────────────
            if in_season and not category.is_active:
                category.is_active = True
                # Skip full_clean on save to avoid slug/name re-validation noise
                Category.objects.filter(pk=category.pk).update(is_active=True)

                # Restore products that only belong to this category (or now have an active category)
                for product in category.products.filter(is_active=False):
                    if product.categories.filter(is_active=True).count() > 0:
                        Product.objects.filter(pk=product.pk).update(is_active=True)

                activated += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ Activated: {category.name}"))

            # ── Archive ───────────────────────────────────────────────────────
            elif not in_season and category.is_active:
                Category.objects.filter(pk=category.pk).update(is_active=False)

                # Archive products that now have no active categories left
                for product in category.products.filter(is_active=True):
                    active_cats = product.categories.filter(is_active=True).exclude(
                        pk=category.pk
                    )
                    if not active_cats.exists():
                        Product.objects.filter(pk=product.pk).update(is_active=False)

                archived += 1
                self.stdout.write(self.style.WARNING(f"  ✗ Archived:  {category.name}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Activated: {activated}  |  Archived: {archived}  |  Unchanged: {seasonal_categories.count() - activated - archived}"
            )
        )
