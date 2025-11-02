from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('super_admin', 'Super Admin'),
        ('checkin_admin', 'Check-in Admin'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='checkin_admin')

    @property
    def is_super_admin(self):
        return self.role == 'super_admin'

    @property
    def is_checkin_admin(self):
        return self.role == 'checkin_admin'

    def save(self, *args, **kwargs):
        # 🔹 Automatically sync role with Django permissions
        if self.role == 'super_admin':
            self.is_staff = True
            self.is_superuser = True
        elif self.role == 'checkin_admin':
            self.is_staff = True
            self.is_superuser = False
        super().save(*args, **kwargs)

class AdminActionLog(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    action = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.action} ({self.timestamp.strftime('%Y-%m-%d %H:%M')})"
    
class Participant(models.Model):
    full_name = models.CharField(max_length=200, db_index=True)
    nationality = models.CharField(max_length=100, db_index=True)
    paid = models.BooleanField(default=False, db_index=True)
    free_access = models.BooleanField(default=False, db_index=True)
    is_present = models.BooleanField(default=False, db_index=True)


    # MEALS FOR 7 DAYS
    breakfast_day1 = models.BooleanField(default=False,db_index=True)
    lunch_day1 = models.BooleanField(default=False,db_index=True)
    breakfast_day2 = models.BooleanField(default=False,db_index=True)
    lunch_day2 = models.BooleanField(default=False,db_index=True)
    breakfast_day3 = models.BooleanField(default=False,db_index=True)
    lunch_day3 = models.BooleanField(default=False,db_index=True)
    breakfast_day4 = models.BooleanField(default=False,db_index=True)
    lunch_day4 = models.BooleanField(default=False,db_index=True)
    breakfast_day5 = models.BooleanField(default=False,db_index=True)
    lunch_day5 = models.BooleanField(default=False,db_index=True)
    breakfast_day6 = models.BooleanField(default=False,db_index=True)
    lunch_day6 = models.BooleanField(default=False,db_index=True)
    breakfast_day7 = models.BooleanField(default=False,db_index=True)
    lunch_day7 = models.BooleanField(default=False,db_index=True)
    class Meta:
        indexes = [
            models.Index(fields=['paid', 'free_access']),
            models.Index(fields=['nationality', 'paid']),
            models.Index(fields=['is_present']),
        ]
    created_at = models.DateTimeField(default=timezone.now)  # ← ADD THIS
    
    def __str__(self):
        return self.full_name