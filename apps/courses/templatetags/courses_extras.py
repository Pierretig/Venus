from django import template
from apps.courses.models import Enrollment, LessonProgress
from apps.courses.services import can_user_access_lesson

register = template.Library()


@register.filter(name='is_enrolled_in')
def is_enrolled_in(course, user):
    """Vérifie si l'utilisateur est inscrit à ce cours."""
    if not user or not user.is_authenticated:
        return False
    return Enrollment.objects.filter(
        user=user,
        course=course,
        status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
    ).exists()


@register.simple_tag
def user_course_progress(course, user):
    """Retourne le pourcentage de progression d'un utilisateur pour une formation."""
    if not user or not user.is_authenticated:
        return 0
    enrollment = Enrollment.objects.filter(
        user=user,
        course=course,
        status__in=[Enrollment.Status.ACTIVE, Enrollment.Status.COMPLETED],
    ).first()
    if not enrollment:
        return 0
    return enrollment.get_progress_percentage()


@register.simple_tag
def can_access(lesson, user):
    """Vérifie si l'utilisateur peut accéder à cette leçon."""
    return can_user_access_lesson(user, lesson)


@register.filter(name='is_lesson_completed_by')
def is_lesson_completed_by(lesson, user):
    """Vérifie si une leçon est terminée par l'utilisateur."""
    if not user or not user.is_authenticated:
        return False
    return LessonProgress.objects.filter(
        enrollment__user=user,
        lesson=lesson,
        is_completed=True,
    ).exists()


@register.filter(name='format_minutes')
def format_minutes(total_minutes):
    """Formate des minutes en format lisible (ex: 1h 30min ou 45min)."""
    try:
        minutes = int(total_minutes or 0)
    except (ValueError, TypeError):
        return "0 min"

    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    remaining_min = minutes % 60
    if remaining_min == 0:
        return f"{hours}h"
    return f"{hours}h {remaining_min:02d}min"

