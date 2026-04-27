from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.orders.models import Order
from apps.orders.utils import send_order_reminder_email


class Command(BaseCommand):
    help = "Envoie des emails de rappel pour les commandes non payées."

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-hours",
            type=int,
            default=2,
            help="Heures minimum depuis la création de commande (défaut: 2).",
        )
        parser.add_argument(
            "--max-hours",
            type=int,
            default=26,
            help="Heures maximum depuis la création de commande (défaut: 26).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche les commandes ciblées sans envoyer d'email.",
        )

    def handle(self, *args, **options):
        min_hours = options["min_hours"]
        max_hours = options["max_hours"]
        dry_run = options["dry_run"]

        now = timezone.now()
        oldest = now - timedelta(hours=max_hours)
        newest = now - timedelta(hours=min_hours)

        queryset = Order.objects.filter(
            status="pending",
            payment_status=False,
            created_at__gte=oldest,
            created_at__lte=newest,
        ).exclude(email="")

        sent = 0
        for order in queryset.iterator():
            payment_url = order.payment_url
            if not payment_url:
                continue
            if dry_run:
                self.stdout.write(
                    self.style.WARNING(
                        f"[DRY-RUN] Rappel cible: commande #{order.id} ({order.email})"
                    )
                )
                continue
            if send_order_reminder_email(order, payment_url):
                sent += 1
                self.stdout.write(self.style.SUCCESS(f"Rappel envoyé pour #{order.id}"))

        self.stdout.write(
            self.style.SUCCESS(f"Terminé. Emails envoyés: {sent} / Commandes ciblées: {queryset.count()}")
        )
