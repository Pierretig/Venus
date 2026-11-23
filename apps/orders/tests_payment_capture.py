"""
Tests de la confirmation de paiement, de la capture des révisions, de la réconciliation
et de l'Outbox. Les tests de concurrence (classes « Postgres… ») utilisent de vraies
transactions concurrentes et ne s'exécutent que sur PostgreSQL :
    python manage.py test apps.orders.tests_payment_capture --settings=config.settings_pg_test
"""
import json
import threading
import time
import unittest
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import jwt
from django.contrib.auth.models import User
from django.db import connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.courses.models import AccessGrant, Course, CourseModule, Enrollment, Lesson
from apps.courses.testing import publish_working_copy
from apps.orders import outbox
from apps.orders.models import (
    Order, OrderItem, OutboxEvent, PaymentReconciliation, PaymentRevisionLink,
)
from apps.orders.payment_processing import (
    InvalidPaymentAmountError, PaymentProcessingError, confirm_order_payment,
)
from apps.products.models import Product

postgres_only = unittest.skipUnless(connection.vendor == 'postgresql', "Concurrence réelle : PostgreSQL requis")
SECRET = 'secret_webhook_test'


def make_course(title, publish=True):
    course = Course.objects.create(title=title, description="d", price=Decimal("10000"), status=Course.Status.PUBLISHED)
    module = CourseModule.objects.create(course=course, title="M", order=0)
    Lesson.objects.create(module=module, title=f"{title} L1", content="v1", order=0)
    revision = publish_working_copy(course) if publish else None
    return course, revision


def make_order(user, courses=(), products=()):
    order = Order.objects.create(user=user, email=user.email if user else "guest@test.invalid")
    total = Decimal("0")
    for course in courses:
        OrderItem.objects.create(order=order, course=course, name=course.title, price=Decimal("10000"), quantity=1)
        total += Decimal("10000")
    for product, qty in products:
        OrderItem.objects.create(order=order, product=product, name=product.name, price=product.price, quantity=qty)
        total += product.price * qty
    Order.objects.filter(pk=order.pk).update(total=total, subtotal=total)
    order.refresh_from_db()
    return order


@override_settings(OUTBOX_EAGER_DISPATCH=False)
class PaymentConfirmationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("client", email="client@test.invalid", password="x")
        self.course_a, self.rev_a = make_course("Formation A")
        self.course_b, self.rev_b = make_course("Formation B")

    def test_normal_confirmation(self):
        order = make_order(self.user, [self.course_a])
        confirmed, order, reason = confirm_order_payment(order.id, transaction_ref="CP-1", amount_received="10000", currency="XOF")
        self.assertTrue(confirmed)
        self.assertEqual(reason, "confirmed")
        self.assertIsNotNone(order.paid_at)
        link = PaymentRevisionLink.objects.get(order=order)
        self.assertEqual(link.course_revision_id, self.rev_a.pk)
        self.assertEqual(link.source, PaymentRevisionLink.Source.PAYMENT_CONFIRMATION)
        grant = AccessGrant.objects.get(order_item=link.order_item)
        self.assertEqual(grant.revision_id, self.rev_a.pk)
        self.assertEqual(Enrollment.objects.get(user=self.user).revision_id, self.rev_a.pk)
        self.assertEqual(
            set(OutboxEvent.objects.filter(order=order).values_list('event_type', flat=True)),
            {'PDF_RECEIPT', 'PAYMENT_EMAIL'},
        )

    def test_repeated_notification_keeps_paid_at(self):
        order = make_order(self.user, [self.course_a])
        confirm_order_payment(order.id, transaction_ref="CP-2", amount_received="10000", currency="XOF")
        first_paid_at = Order.objects.get(pk=order.pk).paid_at
        Lesson.objects.filter(module__course=self.course_a).update(content="v2")
        publish_working_copy(self.course_a)  # nouvelle révision publiée entre-temps
        confirmed, _, reason = confirm_order_payment(order.id, transaction_ref="CP-2", amount_received="10000", currency="XOF")
        self.assertFalse(confirmed)
        self.assertEqual(reason, "already_paid")
        self.assertEqual(Order.objects.get(pk=order.pk).paid_at, first_paid_at)
        self.assertEqual(PaymentRevisionLink.objects.filter(order=order).count(), 1)
        self.assertEqual(PaymentRevisionLink.objects.get(order=order).course_revision_id, self.rev_a.pk)
        self.assertEqual(AccessGrant.objects.filter(user=self.user).count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(order=order).count(), 2)

    def test_wrong_amount_rejected_and_nothing_persisted(self):
        order = make_order(self.user, [self.course_a])
        for amount in ("9999", "10001"):  # insuffisant ET trop-perçu
            with self.assertRaises(InvalidPaymentAmountError):
                confirm_order_payment(order.id, amount_received=amount, currency="XOF")
        order.refresh_from_db()
        self.assertFalse(order.payment_status)
        self.assertIsNone(order.paid_at)
        self.assertFalse(PaymentRevisionLink.objects.exists())
        self.assertFalse(AccessGrant.objects.exists())
        self.assertFalse(OutboxEvent.objects.exists())

    def test_wrong_currency_rejected(self):
        order = make_order(self.user, [self.course_a])
        for currency in ("EUR", "GNF", "CFA"):
            with self.assertRaises(InvalidPaymentAmountError):
                confirm_order_payment(order.id, amount_received="10000", currency=currency)
        self.assertFalse(Order.objects.get(pk=order.pk).payment_status)

    def test_duplicate_reference_rejected(self):
        first = make_order(self.user, [self.course_a])
        confirm_order_payment(first.id, transaction_ref="CP-DUP", amount_received="10000", currency="XOF")
        second = make_order(self.user, [self.course_b])
        with self.assertRaises(PaymentProcessingError):
            confirm_order_payment(second.id, transaction_ref="CP-DUP", amount_received="10000", currency="XOF")
        self.assertFalse(Order.objects.get(pk=second.pk).payment_status)

    def test_multiple_courses_each_line_has_own_revision(self):
        order = make_order(self.user, [self.course_b, self.course_a])
        confirm_order_payment(order.id, amount_received="20000", currency="XOF")
        links = {link.course_id: link for link in PaymentRevisionLink.objects.filter(order=order)}
        self.assertEqual(links[self.course_a.pk].course_revision_id, self.rev_a.pk)
        self.assertEqual(links[self.course_b.pk].course_revision_id, self.rev_b.pk)
        self.assertEqual(AccessGrant.objects.filter(user=self.user, status='active').count(), 2)

    def test_course_without_published_revision(self):
        unpublished, _ = make_course("Sans révision", publish=False)
        order = make_order(self.user, [unpublished, self.course_a])
        confirmed, order, _ = confirm_order_payment(order.id, amount_received="20000", currency="XOF")
        self.assertTrue(confirmed)  # le paiement externe est acquis : la commande est payée
        item = order.items.get(course=unpublished)
        self.assertFalse(PaymentRevisionLink.objects.filter(order_item=item).exists())
        self.assertFalse(AccessGrant.objects.filter(course=unpublished).exists())
        rec = PaymentReconciliation.objects.get(order=order, kind='no_published_revision')
        self.assertEqual(rec.order_item_id, item.pk)
        # L'autre formation de la commande est attribuée normalement.
        self.assertTrue(AccessGrant.objects.filter(course=self.course_a, user=self.user).exists())

        # Résolution : après publication, l'administration capture la révision publiée.
        revision = publish_working_copy(unpublished)
        from apps.orders.payment_processing import capture_course_revisions
        with transaction.atomic():
            locked = Order.objects.select_for_update().get(pk=order.pk)
            capture_course_revisions(locked, source=PaymentRevisionLink.Source.RECONCILIATION)
        self.assertEqual(PaymentRevisionLink.objects.get(order_item=item).course_revision_id, revision.pk)
        self.assertTrue(AccessGrant.objects.filter(course=unpublished, user=self.user).exists())

    def test_outbox_atomic_with_payment(self):
        product = Product.objects.create(name="Rare", price=Decimal("500"), stock=0)
        order = make_order(self.user, [self.course_a], products=[(product, 1)])
        with self.assertRaises(PaymentProcessingError):
            confirm_order_payment(order.id, amount_received=str(order.total), currency="XOF")
        self.assertFalse(OutboxEvent.objects.exists())
        self.assertFalse(PaymentRevisionLink.objects.exists())
        self.assertFalse(AccessGrant.objects.exists())
        self.assertIsNone(Order.objects.get(pk=order.pk).paid_at)

    def test_admin_marks_paid_captures_revision(self):
        order = make_order(self.user, [self.course_a])
        order.status = 'paid'
        order.save()
        order.refresh_from_db()
        self.assertTrue(order.stock_updated)
        self.assertIsNotNone(order.paid_at)
        link = PaymentRevisionLink.objects.get(order=order)
        self.assertEqual(link.source, PaymentRevisionLink.Source.ADMIN_FULFILLMENT)
        self.assertEqual(link.course_revision_id, self.rev_a.pk)


@override_settings(CASHPAY_SECRET_WEBHOOK=SECRET, OUTBOX_EAGER_DISPATCH=False)
class WebhookAndReconciliationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("client", email="client@test.invalid", password="x")
        self.course, self.revision = make_course("Formation W")
        self.order = make_order(self.user, [self.course])
        Order.objects.filter(pk=self.order.pk).update(paygate_tx_id="CP-REF-1")

    def _post(self, claims):
        token = jwt.encode(claims, SECRET, algorithm='HS256')
        return self.client.post(reverse('orders:cashpay_webhook'), data=json.dumps({'token': token}),
                                content_type='application/json')

    def test_webhook_paid_exact_amount(self):
        response = self._post({'merchant_reference': str(self.order.id), 'order_reference': 'CP-REF-1',
                               'state': 'Paid', 'amount': 10000, 'currency': 'XOF'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Order.objects.get(pk=self.order.pk).payment_status)
        self.assertTrue(PaymentRevisionLink.objects.filter(order=self.order).exists())

    def test_webhook_wrong_currency_records_reconciliation(self):
        response = self._post({'merchant_reference': str(self.order.id), 'order_reference': 'CP-REF-1',
                               'state': 'Paid', 'amount': 10000, 'currency': 'EUR'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.get(pk=self.order.pk).payment_status)
        self.assertTrue(PaymentReconciliation.objects.filter(order=self.order, kind='amount_mismatch').exists())

    def test_webhook_amount_verified_with_api_when_ambiguous(self):
        with patch('apps.orders.cashpay_service.CashPayService.get_order_status') as api:
            api.return_value = {'state': 'Paid', 'billed_amount': 9000, 'amount': 0, 'currency': 'XOF'}
            response = self._post({'merchant_reference': str(self.order.id), 'order_reference': 'CP-REF-1',
                                   'state': 'Paid', 'amount': 0})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.get(pk=self.order.pk).payment_status)
        self.assertTrue(PaymentReconciliation.objects.filter(order=self.order, kind='amount_mismatch').exists())

    def test_webhook_partial_or_excess_not_confirmed(self):
        response = self._post({'merchant_reference': str(self.order.id), 'state': 'Excess', 'amount': 12000})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.get(pk=self.order.pk).payment_status)
        self.assertTrue(PaymentReconciliation.objects.filter(order=self.order, kind='provider_state').exists())

    def test_external_paid_but_internal_confirmation_failed(self):
        product = Product.objects.create(name="Épuisé", price=Decimal("1000"), stock=0)
        OrderItem.objects.create(order=self.order, product=product, name="Épuisé", price=Decimal("1000"), quantity=1)
        Order.objects.filter(pk=self.order.pk).update(total=Decimal("11000"))
        claims = {'merchant_reference': str(self.order.id), 'order_reference': 'CP-REF-1',
                  'state': 'Paid', 'amount': 11000, 'currency': 'XOF'}
        for _ in range(2):  # notification répétée : un seul incident ouvert, occurrences incrémentées
            response = self._post(claims)
            self.assertEqual(response.status_code, 400)
        order = Order.objects.get(pk=self.order.pk)
        self.assertFalse(order.payment_status)
        self.assertFalse(PaymentRevisionLink.objects.exists())
        rec = PaymentReconciliation.objects.get(order=order, kind='confirmation_failed')
        self.assertEqual(rec.status, 'open')
        self.assertEqual(rec.occurrences, 2)
        self.assertIn('InsufficientStockError', rec.details['error'])

    def test_paid_on_cancelled_order_records_reconciliation(self):
        Order.objects.filter(pk=self.order.pk).update(status='cancelled')
        response = self._post({'merchant_reference': str(self.order.id), 'order_reference': 'CP-REF-1',
                               'state': 'Paid', 'amount': 10000, 'currency': 'XOF'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(PaymentReconciliation.objects.filter(order=self.order, kind='paid_on_closed_order').exists())

    def test_polling_without_billed_amount_does_not_confirm(self):
        from django.core import signing
        token = signing.dumps(self.order.id, salt='cashpay-return')
        url = reverse('orders:cashpay_payment_status', args=[self.order.id]) + f"?token={token}"
        with patch('apps.orders.cashpay_service.CashPayService.get_order_status') as api:
            api.return_value = {'state': 'Paid'}
            data = self.client.get(url).json()
        self.assertEqual(data['status'], 'pending')
        self.assertFalse(Order.objects.get(pk=self.order.pk).payment_status)
        self.assertTrue(PaymentReconciliation.objects.filter(order=self.order, kind='amount_unverified').exists())


class OutboxWorkerTests(TestCase):
    def setUp(self):
        user = User.objects.create_user("client", email="client@test.invalid", password="x")
        self.order = Order.objects.create(user=user, email=user.email, total=Decimal("1"))

    def _event(self, key="k1", event_type=OutboxEvent.EventType.PAYMENT_EMAIL):
        return OutboxEvent.objects.create(order=self.order, event_type=event_type, idempotency_key=key)

    def test_retry_after_temporary_error(self):
        event = self._event()
        with patch.dict(outbox.HANDLERS, {OutboxEvent.EventType.PAYMENT_EMAIL: lambda e: (_ for _ in ()).throw(RuntimeError("SMTP KO"))}):
            self.assertEqual(outbox.process_batch(), 1)
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxEvent.Status.PENDING)
        self.assertEqual(event.attempts, 1)
        self.assertIn("SMTP KO", event.last_error)
        self.assertGreater(event.available_at, timezone.now())
        self.assertEqual(outbox.process_batch(), 0)  # backoff : pas encore disponible

        OutboxEvent.objects.filter(pk=event.pk).update(available_at=timezone.now() - timedelta(seconds=1))
        with patch.dict(outbox.HANDLERS, {OutboxEvent.EventType.PAYMENT_EMAIL: lambda e: None}):
            outbox.process_batch()
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxEvent.Status.SUCCESS)
        self.assertEqual(event.attempts, 2)

    def test_max_attempts_then_failed(self):
        event = self._event()
        OutboxEvent.objects.filter(pk=event.pk).update(attempts=outbox.MAX_ATTEMPTS - 1)
        with patch.dict(outbox.HANDLERS, {OutboxEvent.EventType.PAYMENT_EMAIL: lambda e: (_ for _ in ()).throw(RuntimeError("KO"))}):
            outbox.process_batch()
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxEvent.Status.FAILED)

    def test_expired_lease_is_reclaimed_and_old_worker_cannot_finish(self):
        event = self._event()
        events, old_token = outbox.claim_events()
        self.assertEqual([e.pk for e in events], [event.pk])
        self.assertEqual(outbox.claim_events()[0], [])  # lease active : non réclamable
        OutboxEvent.objects.filter(pk=event.pk).update(locked_until=timezone.now() - timedelta(seconds=1))
        reclaimed, new_token = outbox.claim_events()
        self.assertEqual([e.pk for e in reclaimed], [event.pk])
        self.assertFalse(outbox._finish(events[0], old_token))  # l'ancien worker a perdu sa lease
        self.assertTrue(outbox._finish(reclaimed[0], new_token))
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxEvent.Status.SUCCESS)
        self.assertEqual(event.attempts, 2)

    def test_idempotency_key_unique(self):
        self._event("same")
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._event("same")


# =============================================================================
# CONCURRENCE RÉELLE (PostgreSQL, transactions distinctes)
# =============================================================================

def _run_threads(*targets):
    threads = [threading.Thread(target=t) for t in targets]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)


@postgres_only
@override_settings(OUTBOX_EAGER_DISPATCH=False)
class PostgresConcurrencyTests(TransactionTestCase):

    def setUp(self):
        self.user = User.objects.create_user("client", email="client@test.invalid", password="x")
        self.course, self.rev1 = make_course("Formation C")

    def test_double_concurrent_confirmation(self):
        order = make_order(self.user, [self.course])
        results = []

        def worker():
            try:
                results.append(confirm_order_payment(order.id, transaction_ref="CP-C", amount_received="10000", currency="XOF")[2])
            except Exception as exc:  # résultat inspecté par l'assertion
                results.append(exc)
            finally:
                connections.close_all()

        _run_threads(worker, worker)
        self.assertEqual(sorted(results), ["already_paid", "confirmed"])
        self.assertEqual(PaymentRevisionLink.objects.count(), 1)
        self.assertEqual(AccessGrant.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(event_type='PAYMENT_EMAIL').count(), 1)

    def test_publication_concurrent_with_payment(self):
        """
        La publication verrouille Course et ne valide qu'après un délai ; la confirmation
        concurrente attend ce verrou puis capture la révision effectivement publiée.
        """
        from apps.courses import revisions as wf
        Lesson.objects.filter(module__course=self.course).update(content="v2")
        reviewer = User.objects.get(username="revision_reviewer_test")
        draft = wf.create_draft_revision(self.course, reviewer)
        rev2 = wf.approve_revision(wf.submit_revision(draft, reviewer), reviewer)
        order = make_order(self.user, [self.course])
        locked = threading.Event()
        results = {}

        def publisher():
            try:
                with transaction.atomic():
                    wf.publish_revision(rev2, reviewer)  # verrou Course acquis ici
                    locked.set()
                    time.sleep(1.0)                      # publication encore non validée
            finally:
                connections.close_all()

        def payer():
            try:
                locked.wait(10)
                started = time.monotonic()
                confirm_order_payment(order.id, amount_received="10000", currency="XOF")
                results['waited'] = time.monotonic() - started
            finally:
                connections.close_all()

        _run_threads(publisher, payer)
        link = PaymentRevisionLink.objects.get(order=order)
        self.assertEqual(link.course_revision_id, rev2.pk)
        self.assertGreater(results['waited'], 0.5)  # a bien attendu le verrou de publication

    def test_two_workers_never_claim_same_event(self):
        order = make_order(self.user)
        for i in range(30):
            OutboxEvent.objects.create(order=order, event_type='PAYMENT_EMAIL', idempotency_key=f"k{i}")
        claimed = {1: [], 2: []}
        barrier = threading.Barrier(2)

        def worker(n):
            def run():
                try:
                    barrier.wait(5)
                    for _ in range(5):
                        events, _token = outbox.claim_events(limit=4)
                        claimed[n].extend(e.pk for e in events)
                finally:
                    connections.close_all()
            return run

        _run_threads(worker(1), worker(2))
        self.assertFalse(set(claimed[1]) & set(claimed[2]))
        self.assertEqual(len(claimed[1]) + len(claimed[2]), 30)
        self.assertEqual(OutboxEvent.objects.filter(attempts=1, status='PROCESSING').count(), 30)
