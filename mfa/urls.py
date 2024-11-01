from django.urls import path

from mfa.views import *

urlpatterns = [
    path('setup/fingerprint', setup_fingerprint, name='setup-fingerprint'),
    path('setup/face-id', setup_face, name='setup-face' ),
]