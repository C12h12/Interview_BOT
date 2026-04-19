from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    interview_type = models.CharField(max_length=255, blank=True, null=True)
    interview_difficulty = models.CharField(max_length=255, blank=True, null=True)
    jd_file = models.FileField(upload_to='jds/', blank=True, null=True)
    resume_file = models.FileField(upload_to='resumes/', blank=True, null=True)
    current_round = models.CharField(max_length=20, default='none') # none, technical, hr, completed
    active_invitation = models.ForeignKey('InterviewInvitation', null=True, blank=True, on_delete=models.SET_NULL)

class DemoConfig(models.Model):
    demo_duration_seconds = models.IntegerField(default=600)
    default_jd_text = models.TextField(default="Default Job Description for interviews.")

class ChatAccess(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    demo_used = models.BooleanField(default=False)
    time_remaining_seconds = models.IntegerField(default=0)

    def total_remaining(self):
        return self.time_remaining_seconds

    def grant_demo(self, seconds):
        self.time_remaining_seconds += seconds
        self.save()
import uuid

class InterviewInvitation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    difficulty = models.CharField(max_length=50, default='medium')
    round_type = models.CharField(max_length=50, default='technical') # technical, hr, both
    jd_file = models.FileField(upload_to='invitation_jds/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_used = models.BooleanField(default=False)

    def __str__(self):
        return f"Invite {self.id} ({self.round_type})"

class InterviewReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='reports')
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Report for {self.user.username} on {self.created_at}"
