from django.urls import path, include

from accounts.views import CustomLoginView, CustomSignupView, logout_confirmation, mfa_selection, fingerprint_login, face_login
from allauth.account.views import LogoutView


urlpatterns = [

    path('accounts/login/', CustomLoginView.as_view(), name='login'),
    path('accounts/signup/', CustomSignupView.as_view(), name='signup'),
    path('accounts/logout/', LogoutView.as_view(), name='logout'),
    path('accounts/logout/confirm/', logout_confirmation, name='logout_confirmation'),
    path('accounts/mfa-selection/continue/login', mfa_selection, name='mfa-selection' ),
    path('accounts/fingerprint/login', fingerprint_login, name='fingerprint-login'),
    path('accounts/face/login/', face_login, name='face-login'),

    path('accounts/', include('allauth.urls')),

]
