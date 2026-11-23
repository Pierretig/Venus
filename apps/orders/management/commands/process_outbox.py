"""
Worker Outbox : traite les événements en attente (reçus PDF, emails de confirmation).

Usage :
    python manage.py process_outbox --once            # un lot puis arrêt (cron / tâche planifiée)
    python manage.py process_outbox --loop --sleep 10 # worker continu

Plusieurs instances peuvent tourner simultanément (SELECT … FOR UPDATE SKIP LOCKED + lease).
Un événement dont le worker a été tué redevient disponible à l'expiration de sa lease
(OUTBOX_LEASE_SECONDS) : aucune remise à zéro manuelle des événements PROCESSING n'est nécessaire.
"""
import signal
import time

from django.core.management.base import BaseCommand

from apps.orders.outbox import process_batch


class Command(BaseCommand):
    help = "Traite les événements Outbox disponibles (reçus PDF, emails de confirmation de paiement)."

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help="Traiter un seul lot puis s'arrêter (défaut).")
        parser.add_argument('--loop', action='store_true', help="Boucler indéfiniment.")
        parser.add_argument('--batch', type=int, default=20, help="Taille d'un lot (défaut : 20).")
        parser.add_argument('--sleep', type=float, default=10.0, help="Pause entre deux lots vides en mode --loop.")

    def handle(self, *args, **options):
        batch = max(1, options['batch'])
        if not options['loop']:
            n = process_batch(limit=batch)
            self.stdout.write(f"{n} événement(s) traité(s).")
            return

        stop = {'requested': False}

        def _stop(signum, frame):
            stop['requested'] = True
        signal.signal(signal.SIGTERM, _stop)
        signal.signal(signal.SIGINT, _stop)

        self.stdout.write("Worker Outbox démarré.")
        while not stop['requested']:
            n = process_batch(limit=batch)
            if n == 0:
                time.sleep(options['sleep'])
        self.stdout.write("Worker Outbox arrêté proprement.")
