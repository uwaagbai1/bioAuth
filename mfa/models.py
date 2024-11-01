from django.db import models
from django.contrib.auth.models import User

class MFAProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="mfaprofile")
    face_data = models.BinaryField(blank=True, null=True, editable=True)
    fingerprint_data = models.BinaryField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s profile"
