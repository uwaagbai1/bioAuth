from django.urls import path
from . import views

urlpatterns = [
    path('', views.profile_home, name='profile-home'),
    path('acccount/update', views.account_update_view, name='account-update'),
    path('account/information', views.account_information, name='account-information'),
]
