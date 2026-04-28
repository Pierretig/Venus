from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('contact/', views.contact_view, name='contact'),
    path('a-propos/', views.about, name='about'),
    path('confidentialite-et-conditions/', views.confidentialite, name='privacy'),
    path('foire-aux-questions/', views.faq, name='faq'),
    path('conditions-generales-de-vente/', views.cgv_view, name='cgv'),

    # Proxy sécurisé pour servir les images Cloudinary avec watermark
    # Usage : /media/image/<app_label>/<model_name>/<pk>/<field_name>/
    path(
        'media/image/<str:app_label>/<str:model_name>/<int:pk>/<str:field_name>/',
        views.serve_image,
        name='serve_image',
    ),
]
