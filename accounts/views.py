import json
import numpy as np
import struct
import datetime

from django.contrib.auth import login, authenticate
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.core.cache import cache

from allauth.account.views import LoginView, SignupView
from functools import wraps

from mfa.models import MFAProfile

# def rate_limit_logins(view_func):
#     @wraps(view_func)
#     def wrapped(request, *args, **kwargs):
#         ip = request.META.get('REMOTE_ADDR')
#         key = f'login_attempts:{ip}'
        
#         # Get current attempts from cache
#         attempts = cache.get(key, 0)
        
#         if attempts >= 5:  # Max 5 attempts per 15 minutes
#             return JsonResponse({
#                 'status': 'error',
#                 'message': 'Too many login attempts. Please try again later.'
#             }, status=429)
            
#         # Increment attempts
#         cache.set(key, attempts + 1, 900)  # 15 minutes timeout
        
#         return view_func(request, *args, **kwargs)
#     return wrapped

def check_temp_auth(request):
    temp_auth = request.session.get('temp_auth', False)
    timestamp = request.session.get('temp_auth_timestamp')
    if not temp_auth or not timestamp:
        return False
    auth_time = datetime.datetime.fromtimestamp(float(timestamp))
    if datetime.datetime.now() - auth_time > datetime.timedelta(minutes=5):
        request.session.pop('temp_auth', None)
        request.session.pop('temp_auth_timestamp', None)
        request.session.pop('auth_email', None)
        return False
    return True

def require_anonymous(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            messages.warning(request, "You are already logged in.")
            return redirect(reverse('profile-home'))
        return view_func(request, *args, **kwargs)
    return wrapper

def require_temp_auth(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not check_temp_auth(request):
            messages.error(request, 'Please log in first.')
            return redirect(reverse('login'))
        return view_func(request, *args, **kwargs)
    return wrapper

def is_live_face(face_descriptor):
    try:
        descriptor_array = np.array(face_descriptor)        
        variation = np.std(descriptor_array)
        if variation < 0.1:
            return False
        return True
    except:
        return False

def log_failed_login_attempt(user, method, request):
    try:
        print(f"Failed login attempt for user {user.email} using {method} from IP {request.META.get('REMOTE_ADDR')}")
    except:
        pass

class CustomLoginView(LoginView):
    template_name = 'account/login.html'
    
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            messages.warning(request, "You are already logged in.")
            return redirect(reverse('profile-home'))
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        email = form.cleaned_data.get('login')
        password = form.cleaned_data.get('password')
        user = authenticate(self.request, username=email, password=password)
        if user is not None:
            self.request.session['temp_auth'] = True
            self.request.session['temp_auth_timestamp'] = datetime.datetime.now().timestamp()
            self.request.session['auth_email'] = email
            return redirect('mfa-selection')
        else:
            messages.error(self.request, "Invalid login credentials.")
            return super().form_invalid(form)

class CustomSignupView(SignupView):
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

@require_temp_auth
def mfa_selection(request):
    email = request.session.get('auth_email') 
    if not email:
        return redirect(reverse('login'))
    try:
        user = User.objects.get(email=email)
        mfa_profile, created = MFAProfile.objects.get_or_create(user=user)
        if not mfa_profile.fingerprint_data and not mfa_profile.face_data:
            user.backend = 'allauth.account.auth_backends.AuthenticationBackend'
            login(request, user)
            messages.warning(request, "Please set up MFA for enhanced security")
            return redirect(reverse('profile-home'))
            
        context = {
            'profile_first_name': user.profile.first_name,
            'profile_last_name': user.profile.last_name,
            'profile_picture': user.profile.profile_picture,
            'mfa_options': {
                'fingerprint': bool(mfa_profile.fingerprint_data),
                'face_id': bool(mfa_profile.face_data),
            }
        }
        return render(request, 'account/mfa-selection.html', context)
    except (User.DoesNotExist, MFAProfile.DoesNotExist):
        messages.error(request, 'User or MFA profile not found')
        return redirect(reverse('login'))

@csrf_exempt
# @rate_limit_logins
@require_temp_auth
def face_login(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            face_descriptor = data.get("faceDescriptor")
            email = data.get("email") or request.session.get('auth_email')
            
            if not face_descriptor or not email:
                return JsonResponse({
                    "status": "error",
                    "message": "Missing face data or email"
                }, status=400)
                
            try:
                user = User.objects.get(email=email)
                mfa_profile = MFAProfile.objects.get(user=user)
                
                if not mfa_profile.face_data:
                    return JsonResponse({
                        "status": "error",
                        "message": "Face ID not set up for this user"
                    }, status=400)
                    
                input_face_binary = convert_array_to_binary(face_descriptor)
                stored_face_array = convert_binary_to_array(mfa_profile.face_data)
                input_face_array = convert_binary_to_array(input_face_binary)
                
                distance = np.linalg.norm(stored_face_array - input_face_array)
                threshold = 0.4
                if distance < threshold:
                    if not is_live_face(face_descriptor):
                        return JsonResponse({
                            "status": "error",
                            "message": "Live face check failed"
                        }, status=401)
                        
                    user.backend = 'allauth.account.auth_backends.AuthenticationBackend'
                    login(request, user)
                    messages.success(request, "Face Authentication Successful")
                    
                    request.session.pop('temp_auth', None)
                    request.session.pop('temp_auth_timestamp', None)
                    request.session.pop('auth_email', None)
                    
                    return JsonResponse({
                        "status": "success",
                        "redirect_url": reverse('profile-home')
                    })
                else:
                    log_failed_login_attempt(user, 'face_id', request)
                    return JsonResponse({
                        "status": "error",
                        "message": "Face verification failed"
                    }, status=401)
                    
            except User.DoesNotExist:
                return JsonResponse({
                    "status": "error",
                    "message": "User not found"
                }, status=404)
            except MFAProfile.DoesNotExist:
                return JsonResponse({
                    "status": "error",
                    "message": "MFA profile not found"
                }, status=404)
        except json.JSONDecodeError:
            return JsonResponse({
                "status": "error",
                "message": "Invalid JSON data"
            }, status=400)
        except Exception as e:
            return JsonResponse({
                "status": "error",
                "message": str(e)
            }, status=500)

    return render(request, 'account/face-login.html')

@require_temp_auth
# @rate_limit_logins
def fingerprint_login(request):
    email = request.session.get('auth_email')
    try:
        user = User.objects.get(email=email)
        mfa_profile = MFAProfile.objects.get(user=user)
        if not mfa_profile.fingerprint_data:
            messages.error(request, "Fingerprint not set up for this user")
            return redirect(reverse('mfa-selection'))
    except (User.DoesNotExist, MFAProfile.DoesNotExist):
        messages.error(request, "User profile not found")
        return redirect(reverse('login'))
        
    return render(request, 'account/fingerprint-login.html')

def convert_array_to_binary(array_data):
    if isinstance(array_data, list):
        array_data = np.array(array_data, dtype=np.float32)
    return struct.pack('f' * len(array_data), *array_data)

def convert_binary_to_array(binary_data):
    float_count = len(binary_data) // struct.calcsize('f')
    unpacked_data = struct.unpack('f' * float_count, binary_data)
    return np.array(unpacked_data, dtype=np.float32)

@login_required
def logout_confirmation(request):
    return render(request, 'account/logout_confirmation.html')