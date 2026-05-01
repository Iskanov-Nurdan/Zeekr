from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=255, blank=True)
    language = models.CharField(max_length=20, default="ru")
    country = models.CharField(max_length=120, blank=True)
    notifications_enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.display_name or self.user.get_username()

