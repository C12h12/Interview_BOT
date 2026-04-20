from django.shortcuts import render, redirect
from django.core.mail import send_mail
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
from django.http import HttpResponse, FileResponse
from .utils import render_to_pdf
from django.core.mail import EmailMessage
from .models import DemoConfig, ChatAccess, InterviewReport

def interview_practice(request):
    if not request.user.is_authenticated:
        return redirect('register')
    return render(request, 'interview/hr_dashboard.html')

@login_required
@csrf_exempt
def generate_invite(request):
    from .models import InterviewInvitation
    if request.method == "POST":
        difficulty = request.POST.get('difficulty', 'medium').lower()
        round_type = request.POST.get('round_type', 'technical').lower()
        jd_file = request.FILES.get('jd_file')

        if not jd_file:
            return JsonResponse({"error": "JD file is mandatory"}, status=400)

        invite = InterviewInvitation.objects.create(
            difficulty=difficulty,
            round_type=round_type,
            jd_file=jd_file
        )
        full_url = request.build_absolute_uri(f"/invite/{invite.id}/")
        return JsonResponse({"url": full_url})
    return JsonResponse({"error": "Invalid"}, status=400)

@login_required
def candidate_landing(request, token):
    from .models import InterviewInvitation
    try:
        invite = InterviewInvitation.objects.get(id=token)
    except:
        messages.error(request, "Invalid or expired invitation link.")
        return redirect('interview_practice')
        
    if request.method == "POST":
        resume_file = request.FILES.get("resumeFile")
        if resume_file:
            user = request.user
            user.resume_file.save(resume_file.name, resume_file)
            
            # Setup interview state based on invitation
            user.interview_difficulty = invite.difficulty
            
            if invite.round_type.lower() == 'both':
                user.current_round = 'technical'
                user.interview_type = 'both'
            elif invite.round_type.lower() == 'all':
                user.current_round = 'aptitude'
                user.interview_type = 'all'
            else:
                user.current_round = invite.round_type.lower()
                user.interview_type = invite.round_type.lower()
                
            user.active_invitation = invite
            user.save()
            
            # Grant demo time for current dev requirements (60s per round)
            if invite.round_type == 'both':
                duration = 120
            elif invite.round_type == 'all':
                duration = 180
            else:
                duration = 60
            access, _ = ChatAccess.objects.get_or_create(user=user)
            access.time_remaining_seconds = duration
            access.save()
            
            return redirect('interview_page')
            
    return render(request, 'interview/candidate_landing.html', {'invite': invite})


def interview_page(request):
    user = request.user
    if user.current_round == 'none' or user.current_round == 'completed':
        # Default behavior for manual setup
        i_type = getattr(user, 'interview_type', 'technical')
        if i_type == "technical": r_name = "Technical"
        elif i_type == "hr": r_name = "HR"
        elif i_type == "aptitude" or i_type == "all": r_name = "Aptitude"
        else: r_name = "Technical" # Fallback
    else:
        # Invitation flow behavior
        i_type = user.current_round
        if i_type == "technical": r_name = "Technical"
        elif i_type == "hr": r_name = "HR"
        elif i_type == "aptitude": r_name = "Aptitude"
        else: r_name = i_type.capitalize()
    
    context = {
        'chat_socket_url': settings.CHAT_SOCKET_URL,
        'heading_title': r_name
    }
    return render(request, 'interview/interview_page.html', context)

@login_required
def invite_interview(request):
    if request.method == "POST":
        resume_file = request.FILES.get("resumeFile")
        if resume_file:
            user = request.user
            user.resume_file.save(resume_file.name, resume_file)
            
            # Start with Technical Round
            user.current_round = 'technical'
            user.interview_type = 'technical' # Sync for compatibility
            user.interview_difficulty = 'medium' # Default for invites
            user.save()
            
            # Grant demo time if needed
            cfg = DemoConfig.objects.first()
            access, created = ChatAccess.objects.get_or_create(user=user)
            if access.total_remaining() <= 0:
                access.grant_demo(cfg.demo_duration_seconds)
            
            return redirect('interview_page')
            
    return render(request, 'interview/invite_interview.html')

@login_required
@csrf_exempt
def save_demo_inputs(request):
    if request.method == "POST":
        interview_type = request.POST.get("interviewType")
        difficulty = request.POST.get("difficulty")
        jd_file = request.FILES.get("jdFile")
        resume_file = request.FILES.get("resumeFile")

        user = request.user
        user.interview_type = interview_type
        user.interview_difficulty = difficulty
        user.current_round = 'none' # Reset for re-initialization in consumer

        if jd_file:
            user.jd_file.save(jd_file.name, jd_file)
        if resume_file:
            user.resume_file.save(resume_file.name, resume_file)
        user.save()

        cfg = DemoConfig.objects.first()
        if cfg is None:
            messages.error(request, "Demo is not configured. Contact admin.")
            return redirect("interview_practice")

        access, created = ChatAccess.objects.get_or_create(user=request.user)

        # If newly created or no time left, grant demo time
        if created or access.total_remaining() <= 0:
            access.grant_demo(cfg.demo_duration_seconds)

        if access and not access.demo_used and access.total_remaining() > 0:
            return JsonResponse({"success": True, "redirect": True})

        return JsonResponse({"success": True, "redirect": False})
    return JsonResponse({"error": "Invalid request"}, status=400)

@login_required
def start_demo(request):
    cfg = DemoConfig.objects.first()
    if cfg is None:
        messages.error(request, "Demo is not configured. Contact admin.")
        return redirect('interview_practice')

    access, _ = ChatAccess.objects.get_or_create(user=request.user)

    if access.demo_used:
        messages.error(request, "You have already used the demo.")
        return redirect('interview_practice')

    # Always grant free demo time
    access.grant_demo(cfg.demo_duration_seconds)
    messages.success(request, f"Demo started for {cfg.demo_duration_seconds // 60} minutes.")
    return redirect('interview_page')

@login_required
@csrf_exempt
def send_interview_link(request):
    if request.method == "POST":
        candidate_email = request.POST.get("email")
        invite_url = request.POST.get("url")

        if not candidate_email or not invite_url:
            return JsonResponse({"error": "Email and URL are required"}, status=400)

        subject = "📝 Official Interview Invitation - AI Evaluation Portal"
        message = f"""Dear Candidate,

We are delighted to inform you that your profile has been shortlisted for the initial assessment stage of our selection process.

As part of our precision-driven recruitment workflow, you are invited to a specialized AI-powered evaluation. This session will assess your technical proficiency, logical reasoning, and behavioral dynamics within a simulated professional environment.

📌 Assessment Overview:
------------------------------------------------------------------
- Duration: Approximately 20-30 Minutes
- Format: Interactive AI-Voice Assessment
- Modules: Aptitude, Technical Evaluation & HR Behavioral Round

🔗 Access Your Secure Interview Portal:
{invite_url}

🚀 Preparation Checklist:
- Ensure you are in a quiet, well-lit environment.
- Use a stable internet connection for real-time telemetry.
- Verify your microphone and camera are fully functional.

Please complete this assessment at your earliest convenience. Your performance will be analyzed by our Talent Acquisition team, and you will receive a detailed performance summary immediately upon completion of the session.

Wishing you the very best of luck!

Best Regards,
Global Talent Acquisition Team
NextGen Dynamics Corp | Advanced AI Division
------------------------------------------------------------------
This is an automated transmission. Please do not reply directly to this email.
"""
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [candidate_email],
                fail_silently=False,
            )
            return JsonResponse({"success": "Email sent successfully!"})
        except Exception as e:
            return JsonResponse({"error": f"Failed to send email: {str(e)}"}, status=500)

    return JsonResponse({"error": "Invalid request"}, status=400)

def download_report(request, report_id):
    try:
        report = InterviewReport.objects.get(id=report_id)
        pdf = render_to_pdf('reports/report_pdf.html', {'data': report.data})
        if pdf:
            response = HttpResponse(pdf, content_type='application/pdf')
            filename = f"Interview_Report_{report.data['candidate_details']['name']}.pdf"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
        return HttpResponse("Error generating PDF", status=500)
    except InterviewReport.DoesNotExist:
        return HttpResponse("Report not found", status=404)

@csrf_exempt
def email_report_view(request):
    if request.method == "POST":
        report_id = request.POST.get("report_id")
        to_email = request.POST.get("email")

        if not report_id or not to_email:
            return JsonResponse({"error": "Report ID and Email are required"}, status=400)

        try:
            report = InterviewReport.objects.get(id=report_id)
            pdf_content = render_to_pdf('reports/report_pdf.html', {'data': report.data})
            
            if not pdf_content:
                return JsonResponse({"error": "Failed to generate PDF"}, status=500)

            subject = f"Interview Performance Report - {report.data['candidate_details']['name']}"
            body = f"Please find attached your interview performance report for the session held on {report.data['candidate_details']['date_time']}."
            
            email = EmailMessage(
                subject,
                body,
                settings.DEFAULT_FROM_EMAIL,
                [to_email],
            )
            email.attach(f"Interview_Report.pdf", pdf_content, 'application/pdf')
            email.send()
            
            return JsonResponse({"success": "Report sent successfully!"})
        except InterviewReport.DoesNotExist:
            return JsonResponse({"error": "Report not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": f"Failed to send email: {str(e)}"}, status=500)

    return JsonResponse({"error": "Invalid request"}, status=400)
