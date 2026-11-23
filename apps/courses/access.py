"""
Droits d'accès aux formations (AccessGrant) et synchronisation avec Enrollment.

Politique (décision R2) :
- Achat : un AccessGrant par OrderItem (OneToOne). Réachat = nouveau droit ; les
  droits précédents ne sont jamais réutilisés ni écrasés.
- Gratuit / attribution manuelle : au plus un droit actif par (apprenant, formation, source).
- Révocation (remboursement, annulation, décision admin) : statut REVOKED + date + motif,
  aucune suppression. L'inscription n'est désactivée que si plus aucun droit actif ne subsiste.
- Enrollment reste unique par (apprenant, formation) et porte la révision suivie.

Aucune fonction ici ne choisit une révision par elle-même : la révision est toujours
fournie par l'appelant (capture du paiement ou Course.published_revision lu sous verrou).
"""
import logging

from django.db import transaction
from django.utils import timezone

from .models import AccessGrant, Course, Enrollment

logger = logging.getLogger(__name__)

_ACCESS_STATUSES = (Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED)


class AccessGrantError(Exception):
    pass


def _activate_enrollment(user, course, revision, source, order=None):
    """Crée ou réactive l'inscription pédagogique et fixe la révision suivie si nécessaire."""
    enrollment, created = Enrollment.objects.select_for_update().get_or_create(
        user=user,
        course=course,
        defaults={
            'status': Enrollment.Status.ACTIVE,
            'source': source,
            'order': order,
            'revision': revision,
            'last_activity_at': timezone.now(),
        },
    )
    if created:
        return enrollment, True

    update_fields = []
    if enrollment.status not in _ACCESS_STATUSES:
        # Réactivation : l'apprenant suit désormais la révision du nouveau droit.
        enrollment.status = Enrollment.Status.ACTIVE
        enrollment.source = source
        enrollment.revision = revision
        enrollment.last_activity_at = timezone.now()
        update_fields += ['status', 'source', 'revision', 'last_activity_at']
        if order is not None:
            enrollment.order = order
            update_fields.append('order')
    elif enrollment.revision_id is None:
        # Inscription historique encore active : on n'invente pas sa révision passée,
        # mais le nouveau droit fournit une révision exacte à suivre désormais.
        enrollment.revision = revision
        update_fields.append('revision')
    if update_fields:
        enrollment.save(update_fields=update_fields)
    return enrollment, False


def grant_purchase_access(order_item, revision, granted_by=None):
    """
    Crée le droit d'accès d'une ligne d'achat (idempotent : OneToOne sur order_item).
    Doit être appelé dans la transaction de confirmation, après capture de la révision.
    """
    order = order_item.order
    if order.user_id is None:
        raise AccessGrantError(f"Commande #{order.pk} sans utilisateur : droit d'accès impossible à attribuer.")
    if revision.course_id != order_item.course_id:
        raise AccessGrantError("La révision capturée n'appartient pas à la formation de la ligne.")

    existing = AccessGrant.objects.filter(order_item=order_item).first()
    if existing is not None:
        return existing, False

    enrollment, _ = _activate_enrollment(order.user, order_item.course, revision, Enrollment.Source.CASHPAY, order=order)
    grant = AccessGrant.objects.create(
        user=order.user,
        course=order_item.course,
        revision=revision,
        enrollment=enrollment,
        order_item=order_item,
        source=AccessGrant.Source.CASHPAY,
        granted_by=granted_by,
    )
    logger.info("AccessGrant #%s créé (commande #%s, ligne #%s, révision #%s)",
                grant.pk, order.pk, order_item.pk, revision.pk)
    return grant, True


@transaction.atomic
def grant_non_purchase_access(user, course, source, granted_by=None):
    """
    Accès gratuit ou attribution manuelle : la révision est la révision publiée,
    lue après verrouillage de la formation (point de synchronisation avec la publication).
    """
    if source == AccessGrant.Source.CASHPAY:
        raise AccessGrantError("Un accès payant doit passer par la confirmation de commande.")
    locked = Course.objects.select_for_update().get(pk=course.pk)
    if locked.published_revision_id is None:
        raise AccessGrantError("Cette formation n'a pas de révision publiée : accès impossible.")
    revision = locked.published_revision

    grant = AccessGrant.objects.filter(user=user, course=locked, source=source, status=AccessGrant.Status.ACTIVE).first()
    enrollment, enrollment_created = _activate_enrollment(user, locked, revision, source)
    if grant is None:
        grant = AccessGrant.objects.create(
            user=user, course=locked, revision=revision, enrollment=enrollment,
            source=source, granted_by=granted_by,
        )
    return enrollment, enrollment_created, grant


def _deactivate_enrollment_if_no_active_grant(enrollment):
    if enrollment.access_grants.filter(status=AccessGrant.Status.ACTIVE).exists():
        return False
    if enrollment.status in _ACCESS_STATUSES:
        enrollment.status = Enrollment.Status.CANCELLED
        enrollment.save(update_fields=['status'])
        return True
    return False


def revoke_grant(grant, reason, revoked_by=None):
    """Révoque un droit sans le supprimer (la révision et les tentatives restent intactes)."""
    if grant.status == AccessGrant.Status.REVOKED:
        return False
    grant.status = AccessGrant.Status.REVOKED
    grant.revoked_at = timezone.now()
    grant.revoked_by = revoked_by
    grant.revocation_reason = (reason or "")[:255]
    grant.save(update_fields=['status', 'revoked_at', 'revoked_by', 'revocation_reason'])
    _deactivate_enrollment_if_no_active_grant(grant.enrollment)
    return True


@transaction.atomic
def revoke_order_access(order, reason, revoked_by=None):
    """
    Révocation consécutive à l'annulation ou au remboursement d'une commande.
    - Droits versionnés : révoqués individuellement (historique conservé).
    - Inscriptions historiques sans droit (avant versionnement) rattachées à la commande :
      comportement antérieur conservé (statut CANCELLED).
    """
    from apps.orders.models import Order
    Order.objects.select_for_update().filter(pk=order.pk).first()
    revoked = 0
    for grant in AccessGrant.objects.select_related('enrollment').filter(
        order_item__order=order, status=AccessGrant.Status.ACTIVE
    ).order_by('course_id', 'pk'):
        if revoke_grant(grant, reason, revoked_by=revoked_by):
            revoked += 1

    if order.user_id:
        course_ids = list(order.items.exclude(course__isnull=True).values_list('course_id', flat=True))
        legacy = Enrollment.objects.filter(
            user_id=order.user_id, course_id__in=course_ids, order=order,
            status__in=_ACCESS_STATUSES,
        ).exclude(access_grants__isnull=False)
        revoked += legacy.update(status=Enrollment.Status.CANCELLED)
    return revoked
