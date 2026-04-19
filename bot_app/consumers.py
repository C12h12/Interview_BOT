import json
import time
import tempfile
import os
from channels.generic.websocket import WebsocketConsumer
from bot_app.prompts import get_level_prompt, type_prompt
from bot_app.evaluator import evaluate_answer
from bot_app.generator import generate_next_question, extract_name_from_resume
from bot_app.report_generator import generate_report
from bot_app.models import DemoConfig, ChatAccess, InterviewReport

from bot_app.config import API_KEY
import requests
import fitz  # PyMuPDF

def extract_text_from_file(file_obj):
    if not file_obj:
        return ""
    try:
        filename = file_obj.name.lower()
        if filename.endswith(".pdf"):
            doc = fitz.open(stream=file_obj.read(), filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text()
            return text.strip()
        else:
            # Fallback for .txt or other formats
            return file_obj.read().decode('utf-8', errors='ignore').strip()
    except Exception as e:
        print(f"Extraction Error for {file_obj.name}: {e}")
        return ""

class InterviewConsumer(WebsocketConsumer):
    def connect(self):
        self.user = self.scope["user"]
        self.user.refresh_from_db()
        
        self.accept()
        
        if not self.user.is_authenticated:
            self.send(text_data=json.dumps({"error": "Unauthorized"}))
            self.close()
            return
            
        self.cfg = DemoConfig.objects.first()
        self.access, _ = ChatAccess.objects.get_or_create(user=self.user)
        
        if self.access.total_remaining() <= 0:
            self.send(text_data=json.dumps({"error": "No demo/paid time available. Please purchase or contact admin."}))
            return

        self.total_interview_duration = self.access.total_remaining()
        self.current_round_duration = 60 if self.total_interview_duration >= 120 else self.total_interview_duration
        self.round_start_time = time.time()
        self.start_time = self.round_start_time # for global tracking if needed
        
        # Determine starting round
        if self.user.current_round in ['none', 'completed']:
            start_round = self.user.interview_type or 'technical'
            if start_round == 'all':
                start_round = 'aptitude'
            self.user.current_round = start_round
            self.user.save()

        level = getattr(self.user, 'interview_difficulty', 'Moderate')
        round_type = self.user.current_round
        
        # Get Job Description from the invitation link
        job_desc_text = self.cfg.default_jd_text
        if self.user.active_invitation and self.user.active_invitation.jd_file:
            txt = extract_text_from_file(self.user.active_invitation.jd_file)
            if txt: job_desc_text = txt
        elif self.user.jd_file:
            txt = extract_text_from_file(self.user.jd_file)
            if txt: job_desc_text = txt
            
        resume_text = "Standard resume profile."
        if self.user.resume_file:
            txt = extract_text_from_file(self.user.resume_file)
            if txt: resume_text = txt
        
        # Extract candidate name from resume
        self.candidate_name = extract_name_from_resume(resume_text)
        print(f"DEBUG: Extracted Candidate Name: {self.candidate_name}")
        
        base_prompt = f"""
You are an AI Interview Preparation Assistant. Your role is to simulate a professional interview 
for the candidate, using the provided job description and resume. You must ask relevant, 
context-aware questions and give constructive feedback.
==================================================================
📌 Context
------------------------------------------------------------------
Interview Level: {get_level_prompt(level)}
Current Round: {type_prompt(round_type)}
Job Description (JD): 
{job_desc_text}

Candidate Resume: 
{resume_text}
==================================================================
        """
        self.conversation_history = base_prompt + "\nIMPORTANT: Start the interview by asking the very first question of the current round immediately. No introductory fluff. No appreciation.\nInterviewer:"
        self.evaluation_log = []
        
        # Generate and send first question
        try:
            self.interviewer_question = generate_next_question(self.conversation_history)
        except Exception as e:
            print("Initial Generation Error:", e)
            self.interviewer_question = None

        if not self.interviewer_question:
            # Round-specific fallback questions
            if round_type == 'aptitude':
                self.interviewer_question = "To start with the Aptitude round, here is a logic puzzle: If a train travels at 60km/h for 2 hours and then 80km/h for 1 hour, what is its average speed?"
            elif round_type == 'technical':
                self.interviewer_question = "Welcome! Let's dive into the technical assessment. Can you tell me about the most challenging technical problem you've solved?"
            else:
                self.interviewer_question = "Welcome! Let's start with your background. Tell me about yourself."
            
        self.conversation_history += f" {self.interviewer_question}"
        
        # Send first time update & question
        self.send(text_data=json.dumps({"type": "time_update", "remaining_seconds": self.current_round_duration}))
        self.send(text_data=json.dumps({"question": self.interviewer_question}))

    def disconnect(self, close_code):
        pass
        
    def transcribe_audio(self, bytes_data):
        if not API_KEY:
            return "This is a dummy transcription because OPENAI_API_KEY is not loaded."
            
        # Write to temp webm file
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(bytes_data)
            temp_path = f.name
            
        try:
            with open(temp_path, "rb") as audio_file:
                response = requests.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {API_KEY}"},
                    files={"file": ("audio.webm", audio_file, "audio/webm")},
                    data={"model": "whisper-1"}
                )
                if response.status_code == 200:
                    text = response.json().get("text", "").strip()
                else:
                    print("OpenAI Whisper Error:", response.text)
                    text = "Could not transcribe audio."
        except Exception as e:
            print("STT Error:", e)
            text = "Could not transcribe audio."
        finally:
            os.remove(temp_path)
            
        return text

    def receive(self, text_data=None, bytes_data=None):
        # Refresh user state to ensure we have latest round/type info
        self.user.refresh_from_db()
        print(f"DEBUG: Receive called. Round: {self.user.current_round}, Type: {self.user.interview_type}")

        # Update time
        round_elapsed = time.time() - self.round_start_time
        remaining = max(0, self.current_round_duration - int(round_elapsed))
        print(f"DEBUG: Timer: {remaining}s left in {self.user.current_round} round.")

        self.send(text_data=json.dumps({"type": "time_update", "remaining_seconds": remaining}))
        
        # Pre-calculate next round for transition logic
        interview_type = self.user.interview_type
        current_round = self.user.current_round
        
        next_round = None
        if interview_type == 'all':
            if current_round == 'aptitude': next_round = 'technical'
            elif current_round == 'technical': next_round = 'hr'

        if remaining <= 0 and not next_round:
            print(f"DEBUG: Time Expired and no next round (Current: {current_round}). Finishing session.")
            self.send(text_data=json.dumps({"type": "time_expired", "message": "Time is up!"}))
            self.finish_interview()
            return

        is_time_up = (text_data and json.loads(text_data).get("type") == "time_up")
        
        answer = ""
        if bytes_data:
            answer = self.transcribe_audio(bytes_data)
        elif text_data:
            try:
                data = json.loads(text_data)
                answer = data.get("answer", "")
            except: pass

        if not answer and not is_time_up:
            return
            
        if answer:
            self.send(text_data=json.dumps({"answer": answer})) # Echo back the transcribed answer
            self.conversation_history += f"\nCandidate: {answer}\nInterviewer:"
            
            # Evaluate
            eval_data = evaluate_answer(answer, self.interviewer_question)
            eval_data["question"] = self.interviewer_question
            eval_data["answer"] = answer
            self.evaluation_log.append(eval_data)
        else:
            # Time up with no final answer
            self.conversation_history += f"\nCandidate: [No response, time expired]\nInterviewer:"
        
        # Logic to transition between rounds
        num_evals = len(self.evaluation_log)
        
        try:
            if next_round and (is_time_up or round_elapsed >= self.current_round_duration):
                print(f"🔄 Transitioning {current_round} -> {next_round} (Time Up)")
                self.user.current_round = next_round
                self.user.save()
                
                # Reset round timer
                self.round_start_time = time.time()
                self.current_round_duration = 60
                
                round_display_names = {
                    'technical': 'Technical',
                    'hr': 'HR',
                    'aptitude': 'Aptitude'
                }
                next_round_name = round_display_names.get(next_round, next_round.capitalize())
                
                self.send(text_data=json.dumps({
                    "type": "round_complete", 
                    "message": f"{current_round.capitalize()} Round Complete! Moving to {next_round_name} Round...",
                    "heading": next_round_name
                }))
                
                # Immediate time sync for the next round (60s)
                self.send(text_data=json.dumps({"type": "time_update", "remaining_seconds": 60}))
                
                self.conversation_history += f"\n--- End of {current_round} round. Now START {next_round} ROUND focusing on: {type_prompt(next_round)} ---\nInterviewer:"
                
                default_qs = {
                    'technical': "Great. Let's move to the technical assessment. Can you describe a project you've worked on recently?",
                    'hr': "Great. Let's move to some behavioral questions. Tell me about a challenge you faced."
                }
                self.interviewer_question = generate_next_question(self.conversation_history) or default_qs.get(next_round, "Let's continue focus on next part.")
            
            elif (not next_round) and (is_time_up or round_elapsed >= self.current_round_duration):
                print("🏁 Force Finishing Session (End Early/Time Up)")
                self.finish_interview()
                return
            
            elif round_elapsed >= 55 or num_evals >= 15: # wrap up early per round if needed
                final_prompt = self.conversation_history + "\nInterviewer: Just Ask one very simple wrap-up question to close the session, which do not need any feedback.No appreciation in beginning."
                self.interviewer_question = generate_next_question(final_prompt) or "Thank you for your time today. Do you have any questions for me?"
            else:
                self.interviewer_question = generate_next_question(self.conversation_history) or "Can you expand more on that?"
                
            if not self.interviewer_question:
                self.finish_interview()
                return
                
            self.conversation_history += f" {self.interviewer_question}"
            self.send(text_data=json.dumps({"question": self.interviewer_question}))
        except Exception as e:
            print("Bot Generation Error:", e)
            self.send(text_data=json.dumps({"question": "That's interesting. Can you tell me more about your experience?"}))

    def finish_interview(self):
        try:
            self.user.current_round = 'completed'
            self.user.save()
            
            level = getattr(self.user, 'interview_difficulty', 'Moderate')
            # Dynamically set display mode
            raw_mode = self.user.interview_type or "technical"
            if raw_mode.lower() == "all":
                t_type = "Full Interview (Aptitude, Technical & HR)"
            else:
                t_type = f"{raw_mode.capitalize()} Interview"
            
            final_report = generate_report(level, t_type, self.evaluation_log)
            
            # Format report to match frontend expectations
            summary = {
                "candidate_details": {
                    "name": self.candidate_name or self.user.username,
                    "interview_mode": final_report["candidate_details"]["interview_mode"],
                    "difficulty_level": final_report["candidate_details"]["difficulty_level"],
                    "date_time": final_report["candidate_details"]["date_time"]
                },
                "interview_summary": {
                    "total_questions": len(self.evaluation_log),
                    "summary_text": final_report["interview_summary"]["summary_text"]
                },
                "tech_section": self.evaluation_log,
                "overall": {
                    "average_score": final_report["overall"]["average_score"],
                    "rating": final_report["overall"]["rating"]
                },
                "recommendations": final_report.get("recommendations", [])
            }
            
            # Save report to DB for download/email features
            report = InterviewReport.objects.create(user=self.user, data=summary)
            summary["report_id"] = str(report.id)
            
            self.send(text_data=json.dumps({"type": "session_complete", "summary": summary}))
            self.close()
        except Exception as e:
            print("Error generating conclusion:", e)
            self.send(text_data=json.dumps({"type": "session_complete", "summary": {"candidate_details": {"name": "Test"}} }))
            self.close()
