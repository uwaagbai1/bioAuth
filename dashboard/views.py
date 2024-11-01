import json
import os

from django.core.files.base import ContentFile
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
import base64
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt

from dashboard.forms import *
from mfa.models import MFAProfile

@login_required
def profile_home(request):
    return render(request, 'dashboard/index.html')

@login_required
def account_update_view(request):
    profile = request.user.profile
    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('account-update')
    else:
        form = ProfileUpdateForm(instance=profile)
        print(form.errors)
    return render(request, 'dashboard/account-update.html', {'form': form})

@login_required
def account_information(request):
    profile = request.user.profile
    user = request.user
    context = {
        'profile': profile,
        'user': user,
    }
    return render(request, 'dashboard/account-information.html', context)