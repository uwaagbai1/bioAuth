import json
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from .models import MFAProfile
import struct
import numpy as np
import json
import secrets
from base64 import b64encode


@login_required
def setup_fingerprint(request):
    return render(request, 'mfa/setup-fingerprint.html', {
        'userEmail': request.user.email,
        'userName': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
    })


@login_required
@csrf_protect
def get_challenge(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        challenge = secrets.token_bytes(32)
        request.session['webauthn_challenge'] = b64encode(challenge).decode('utf-8')

        if not request.session.get('webauthn_user_id'):
            request.session['webauthn_user_id'] = b64encode(secrets.token_bytes(16)).decode('utf-8')

        return JsonResponse({
            'challenge': request.session['webauthn_challenge'],
            'userId': request.session['webauthn_user_id']
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@csrf_protect
def register_fingerprint(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        credential_data = json.loads(request.body)

        stored_challenge = request.session.get('webauthn_challenge')
        if not stored_challenge:
            return JsonResponse({'error': 'Invalid challenge'}, status=400)

        mfa_profile, created = MFAProfile.objects.get_or_create(user=request.user)

        credential_binary = json.dumps(credential_data).encode('utf-8')
        mfa_profile.fingerprint_data = credential_binary
        mfa_profile.save()

        request.session.pop('webauthn_challenge', None)
        request.session.pop('webauthn_user_id', None)

        return JsonResponse({'status': 'success'})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


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

            # Convert the array to binary data
            try:
                # Convert the facial data array to bytes
                binary_data = struct.pack('f' * len(facial_data), *facial_data)
            except Exception as e:
                return JsonResponse({
                    "message": f"Invalid facial data format: {str(e)}"
                }, status=400)

            # Get or create MFAProfile
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
    """Convert binary data back to facial descriptor array"""
    float_count = len(binary_data) // struct.calcsize('f')
    return struct.unpack('f' * float_count, binary_data)


def verify_face(stored_face_data, new_face_descriptor):
    if stored_face_data:
        # Convert stored binary data back to array
        stored_descriptor = convert_binary_to_array(stored_face_data)

        # Convert to numpy arrays for distance calculation
        stored_array = np.array(stored_descriptor)
        new_array = np.array(new_face_descriptor)

        # Calculate Euclidean distance
        distance = np.linalg.norm(stored_array - new_array)

        # Typically, a distance < 0.6 indicates the same person
        return distance < 0.6

    return False
