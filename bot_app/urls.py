from django.urls import path
from . import views

from django.shortcuts import redirect
from django.contrib.auth import login
from bot_app.models import CustomUser, DemoConfig

def mock_register(request):
    user, created = CustomUser.objects.get_or_create(username="testuser", defaults={"email": "test@test.com"})
    if created:
        user.set_password("password123")
        user.save()
    
    # Create DemoConfig if it doesn't exist so the interview app doesn't crash
    DemoConfig.objects.get_or_create(id=1, defaults={'demo_duration_seconds': 600})
    
    login(request, user)
    return redirect('interview_practice')

urlpatterns = [
    path('', views.interview_practice, name='interview_practice'),
    path('interview_practice/', views.interview_practice, name='interview_practice'),
    path('interview_page/', views.interview_page, name='interview_page'),
    path('interview/invite/', views.invite_interview, name='invite_interview'),
    path('generate_invite/', views.generate_invite, name='generate_invite'),
    path('invite/<uuid:token>/', views.candidate_landing, name='candidate_landing'),
    path('save_demo_inputs/', views.save_demo_inputs, name='save_demo_inputs'),
    path('start_demo/', views.start_demo, name='start_demo'),
    path('register/', mock_register, name='register'),
    path('send_interview_link/', views.send_interview_link, name='send_interview_link'),
    path('download_report/<uuid:report_id>/', views.download_report, name='download_report'),
    path('email_report/', views.email_report_view, name='email_report'),
]
