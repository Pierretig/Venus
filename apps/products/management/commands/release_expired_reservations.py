from django.core.management.base import BaseCommand

from apps.products.stock_utils import release_expired_reservations


class Command(BaseCommand):
    help = (
        "Libère automatiquement les réservations de stock expirées "
        "(clients qui n'ont pas payé dans les 15 minutes). "
        "À planifier en cron (ex: toutes les 5 minutes)."
    )

    def handle(self, *args, **options):
        count = release_expired_reservations()
        self.stdout.write(
            self.style.SUCCESS(f"{count} réservation(s) expirée(s) libérée(s).")
        )
