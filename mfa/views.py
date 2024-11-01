import json
import numpy as np
import struct

from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_protect, csrf_exempt

from mfa.models import MFAProfile


@login_required
@csrf_exempt
def setup_fingerprint(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            status = data.get('status')

            if status == 'success':

                mfa_profile, created = MFAProfile.objects.get_or_create(user=request.user)
                mfa_profile.fingerprint_enabled = True
                mfa_profile.save()

                return JsonResponse({
                    'status': 'success',
                    'message': 'Fingerprint setup completed successfully'
                })
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': data.get('message', 'Fingerprint setup failed')
                }, status=400)

        except json.JSONDecodeError:
            return JsonResponse({
                'status': 'error',
                'message': 'Invalid request data'
            }, status=400)

        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=500)

    return render(request, 'mfa/setup-fingerprint.html', {
        'userEmail': request.user.email,
        'userName': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
    })

@login_required
@csrf_exempt
def setup_face(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            facial_data = data.get("facialId")
            
            if not facial_data:
                return JsonResponse({
                    "message": "No facial data received."
                }, status=400)            
            try:
                binary_data = struct.pack('f' * len(facial_data), *facial_data)
            except Exception as e:
                return JsonResponse({
                    "message": f"Invalid facial data format: {str(e)}"
                }, status=400)
            
            mfa_profile, created = MFAProfile.objects.get_or_create(user=request.user)
            mfa_profile.face_data = binary_data
            mfa_profile.save()
            
            return JsonResponse({
                "message": "Face ID successfully enrolled.",
                "status": "success"
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                "message": "Invalid JSON data received."
            }, status=400)
        except Exception as e:
            return JsonResponse({
                "message": f"Error processing face enrollment: {str(e)}"
            }, status=500)
    
    return render(request, 'mfa/setup-face.html')

def convert_binary_to_array(binary_data):
    float_count = len(binary_data) // struct.calcsize('f')
    return struct.unpack('f' * float_count, binary_data)

def verify_face(stored_face_data, new_face_descriptor):
    if stored_face_data:
        stored_descriptor = convert_binary_to_array(stored_face_data)        
        stored_array = np.array(stored_descriptor)
        new_array = np.array(new_face_descriptor)        
        distance = np.linalg.norm(stored_array - new_array)        
        return distance < 0.6
    
    return False
