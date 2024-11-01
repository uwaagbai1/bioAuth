from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    profile_picture = models.ImageField(default='default.png', upload_to='profile_pictures')
    job = models.CharField(max_length=30, blank=True)
    about_me = models.TextField(blank=True)
    def __str__(self):
        return f"{self.user.username}'s profile"