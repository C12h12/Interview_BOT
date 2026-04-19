import time, threading
import re
from prompts import get_level_prompt,type_prompt, FOLLOW_UP
from evaluator import evaluate_answer
from generator import generate_next_question
from config import LEVEL_DURATIONS
from report_generator import generate_report


def run_interview(level, type,job_desc_text, resume_text):
    interview_duration = LEVEL_DURATIONS.get(level, 15 * 60)
    interview_end_flag = threading.Event()
    start_time = time.time()

    def end_interview_after_timeout():
        time.sleep(interview_duration)
        interview_end_flag.set()

    def get_time_left():
        elapsed = time.time() - start_time
        remaining = interview_duration - elapsed
        return remaining

    def process_candidate_input(user_input):
        text = user_input.lower()

        # Check for pause/break requests

        # ✅ Check for "X minutes"
        match_min = re.search(r'wait\s*for\s*(\d+)\s*minute', text)
        if match_min:
            minutes = int(match_min.group(1))
            # print(f"🧑‍💼 Interviewer: Sure, take your {minutes} minute(s).")
            time.sleep(minutes * 60)   # pause in seconds
            # print("🧑‍💼 Interviewer: Okay, hope you’re ready now! Let’s continue with the interview.")
            return None

        # ✅ Check for "X seconds"
        match_sec = re.search(r'wait\s*for\s*(\d+)\s*second', text)
        if match_sec:
            seconds = int(match_sec.group(1))
            # print(f"🧑‍💼 Interviewer: Sure, take your {seconds} second(s).")
            time.sleep(seconds)
            # print("🧑‍💼 Interviewer: Okay, hope you’re ready now! Let’s continue with the interview.")
            return None

        # ✅ Generic pause without time
        if "wait" in text or "pause" in text or "break" in text:
            # print("🧑‍💼 Interviewer: Sure, take your time. Let me know when you’re ready.")
            return None

        return user_input

    threading.Thread(target=end_interview_after_timeout, daemon=True).start()

    base_prompt = f"""
You are an AI Interview Preparation Assistant. Your role is to simulate a professional interview 
for the candidate, using the provided job description and resume. You must ask relevant, 
context-aware questions and give constructive feedback.
==================================================================
📌 Context
------------------------------------------------------------------
Interview Level: {get_level_prompt(level)}   # Easy / Moderate / Hard
Interview Type: {type_prompt(type)}   # HR / Technical / Mixed
Job Description (JD): 
{job_desc_text}

Candidate Resume: 
{resume_text}
==================================================================

✅ Do’s (Guidelines for You)
------------------------------------------------------------------
1. Always generate questions that are:
   - Aligned with the job description requirements.
   - Tailored to the candidate’s resume (skills, projects, experience).
   - Cover both **strength areas** (to test depth) and **missing skills** (to test adaptability).

2. Ask one question at a time. 
   - Wait for the candidate’s response before proceeding.
   - Keep follow-up questions contextual (based on candidate’s last answer).

3. Provide constructive feedback after each answer:
   - Score (0–5).
   - Highlight positives (clarity, relevance, technical depth).
   - Suggest improvements (e.g., "Include metrics", "Use STAR format").
   -  Correct grammar, spelling mistakes, and vocabulary errors politely and briefly. 
      Always rephrase the candidate’s incorrect sentence into the correct version 
      (e.g., "He explain me" → "He explained to me").

4. Adapt difficulty:
   - If candidate is strong → increase complexity (system design, edge cases).
   - If candidate struggles → simplify + give hints.

5. Include a balance:
   - **Technical questions** (skills, tools, projects).
   - **Behavioral questions** (communication, teamwork, problem-solving).
   - **Role-specific scenarios**.

6. If the candidate asks a Technical or HR-related question during the interview:
   - Always provide a short, clear, and helpful answer (1–2 sentences only).
   - After answering, politely redirect them back to the interview flow with a transitional line:
     "Now, let’s continue with the interview flow."
   
7. Handling unusual inputs:
     If the candidate provides input that is unintelligible, gibberish, or unrelated (e.g., random characters, meaningless words,tfvhbbnkjnkjjj), do **not repeat it**. Politely acknowledge that the **input was unclear and prompt the candidate to try again or provide a valid answer**. Then continue the interview flow with the same question or guidance. Keep feedback concise and encouraging.
8. Handling pause/break requests:
    If the candidate types "wait", "pause", "break", or a time-based pause 
    (e.g., "wait for 2 minutes"), acknowledge politely and pause the interview.
    After the requested time has passed, automatically resume by saying:
    "Okay, hope you’re ready now! Let’s continue with the interview."
    Then proceed with the next question.

❌ Don’ts (Restrictions)
------------------------------------------------------------------
1. Do not ask irrelevant or random questions outside the JD or resume.
2. Do not overwhelm the candidate with multiple questions at once.
3. If the candidate’s response contains their name, the interviewer must NOT apply any correction to that part of the response. The name segment is completely exempt from feedback.
3. Correct grammar and spelling only in general answers — but NEVER correct, comment on, or suggest improvements to the capitalization, spelling, or formatting of the candidate’s name, even if it appears in lowercase. Treat the name exactly as provided.
4. Do not give full answers immediately if candidate struggles — 
   instead, offer hints or partial guidance first.
5. Do not repeat the same type of question unless for progressive difficulty.
6. Do not criticize harshly — feedback must always be encouraging + actionable.
7. Do not skip any HR or Technical questions asked by the candidate. Always answer them briefly and return to the interview flow.
8. Do not answer any off-topic or irrelevant questions (e.g., food, movies, trivia like "What is idli?").
9. Do not re-answer the previous candidate question after skipping an off-topic one.
   Do not inject a brand-new question immediately. Just return to the normal flow.
10. Do not repeat the candidate's answer back as the interviewer’s question or statement. Always separate candidate input from feedback, and ensure the interviewer only provides evaluation, hints, or the next relevant question.
11. Do not use transition phrases like "Okay, let's proceed", "Alright, moving on","Okay, hope you’re ready now! Let’s continue with the interview.", or similar fillers before giving feedback or asking the next question. 
    Directly provide the feedback or ask the next question instead.
12. Do not use the word "Feedback:" in the interviewer’s responses.Provide the evaluation, score, and suggestions directly without any label or prefix.

🎯 Examples (Follow This Style)
------------------------------------------------------------------
Example Q (Technical): 
"Your resume shows experience with React. Can you explain how you optimized 
component rendering performance in one of your projects?"

Example Feedback (Candidate Answered Well):
"You clearly explained the use of React.memo and lazy loading. 
To improve, mention metrics (e.g., reduced load time by 30%). 
Also, you could phrase it as: 'I optimized rendering by using React.memo, which reduced load time by 30%.'"

Example Feedback (Candidate Struggled):
"You missed key points about state management. Hint: Think about libraries like Redux or Context API. 
SNext time, structure your answer as: challenge → solution → impact."

Example Feedback (Grammar & Spelling Correction):
"Your answer was good, but here’s a small correction: instead of 
'He recieve the data', say 'He received the data'. 
Try to watch out for spelling mistakes like this."

Example Feedback (Vocabulary Correction):
"Clear explanation! Just one word choice improvement: instead of 
'system was very slow', you could say 'the system was inefficient'. 
This makes your answer sound more professional."

Example Feedback (Unclear Answer):
"I couldn’t fully understand your response. Could you please re-answer that question?"

Example Q (Behavioral): 
"Tell me about a time when you had to handle conflicting deadlines between two projects. 
How did you prioritize your tasks?"

==================================================================
Now, start the interview simulation. 
First, greet the candidate with a short, polite one-liner such as:
“ Hi #Candidate_name! I’m your Interview Prep Bot. Let’s begin—can you introduce yourself? ”
"""
    conversation_history = base_prompt + "\nInterviewer:"
    evaluation_log = []

    first_question = generate_next_question(conversation_history)
    # print("\n🧑‍💼 Interviewer:", first_question)
    conversation_history += f" {first_question}"
    interviewer_question = first_question

    while not interview_end_flag.is_set():
        try:
            answer = input("\n🧑 Candidate (type your answer): ")

        except EOFError:
            break

        if not answer:
            # print("\n🛑 No response received. Ending the interview.")
            break

        processed = process_candidate_input(answer)
        if processed is None:
            continue  # skip the rest of loop, wait until candidate is ready
        else:
            answer = processed

        conversation_history += f"\nCandidate: {answer}\nInterviewer:"
        eval_data = evaluate_answer(answer, interviewer_question)
        eval_data["question"] = interviewer_question
        eval_data["answer"] = answer
        evaluation_log.append(eval_data)

        # ✅ Always show time left after each answer
        time_left = get_time_left()
        mins = int(time_left // 60)
        secs = int(time_left % 60)
        
        # ✅ If time is critically low, request final question from LLM
        if time_left < 0.2 * interview_duration or time_left <= 120:
            # print("\n🧑‍💼 Interviewer: We’re almost done with our session, so let’s end with one last question.")
            time.sleep( 0.03* 60)   # pause in seconds

            # Add instruction to conversation history
            final_prompt = conversation_history + "\nInterviewer: Just Ask one very simple wrap-up question to close the session, which do not need any feedback.No appreciation in beginning."
            interviewer_question = generate_next_question(final_prompt)
            # print("🧑‍💼 Interviewer:", interviewer_question)
            conversation_history += f" {interviewer_question}"

            # Candidate's final answer
            final_answer = input("\n🧑 Candidate (type your answer): ")

            eval_data = evaluate_answer(final_answer, interviewer_question)
            eval_data["question"] = interviewer_question
            eval_data["answer"] = final_answer
            evaluation_log.append(eval_data)

            # Conclude interview
            # print("\n🧑‍💼 Interviewer: Thank you for your responses! That concludes this interview prep session. Wishing you the best! 🙌")
            break

        next_question = generate_next_question(conversation_history)
        if not next_question:
            # print("🛑 Interview ended. No further questions.")
            break

        interviewer_question = next_question
        # print("\n🧑‍💼 Interviewer:", interviewer_question)
        conversation_history += f" {interviewer_question}"

    # print("\n🛑 Interview time completed or session ended.")
    
    # ✅ Generate the final report
    final_report = generate_report(level, type, evaluation_log)
    
    # Print or save
    
    return final_report
