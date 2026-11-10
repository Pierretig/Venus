from django.urls import path
from . import views

app_name = 'courses'

urlpatterns = [
    # Catalogue et présentation
    path('', views.course_list, name='course_list'),
    path('mon-espace/', views.student_dashboard, name='student_dashboard'),
    path('<slug:slug>/', views.course_detail, name='course_detail'),

    # Inscription et Paiement
    path('<slug:slug>/acheter/', views.buy_course, name='buy_course'),
    path('<slug:slug>/inscription-gratuite/', views.enroll_free_course, name='enroll_free'),

    # Lecteur de cours et leçons
    path('<slug:course_slug>/lecon/<int:lesson_id>/', views.lesson_view, name='lesson_detail'),
    path('lecon/<int:lesson_id>/terminer/', views.mark_lesson_completed, name='mark_lesson_completed'),

    # Quiz
    path('quiz/<int:quiz_id>/soumettre/', views.submit_quiz, name='submit_quiz'),

    # Certificats
    path('certificat/<str:certificate_code>/telecharger/', views.download_certificate, name='download_certificate'),
    path('verifier/<str:code>/', views.verify_certificate, name='verify_certificate'),
]

