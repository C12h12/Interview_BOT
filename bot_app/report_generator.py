import datetime
import json
import re
from .config import generator

def generate_report(level, interview_type, evaluation_log):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Candidate name detection from first answer
    candidate_name = "N/A"
    name_patterns = [
        r"(?:my name is|i am|i'm|myself|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})",
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"  # fallback: 2–4 capitalized words together
    ]

    for entry in evaluation_log:
        answer = entry.get("answer", "").strip()

        for pattern in name_patterns:
            match = re.search(pattern, answer, flags=re.I)
            if match:
                candidate_name = match.group(1).strip()
                break
        
        if candidate_name != "N/A":
            break


        # --- STRONG FILTERING FOR NON-INTERVIEW QUESTIONS ---
    strict_filler_patterns = [
        r"it's great to meet you",
        r"small correction",
        r"your response was unclear",
        r"i couldn't fully understand",
        r"could you please clarify",
        r"that was not clear",
        r"let me correct you",
        r"your introduction was",
        r"please rephrase",
        r"let's fix that",
        r"based on your previous answer",
        r"your answer had an issue",
        r"the answer is not relevant",
        r"your response is a bit unclear",
        r"good to hear from you",
        r"nice to hear from you",
        r"i appreciate your response",
        r"thanks for sharing",
        r"feedback",
        r"correction",
        r"let me help you with that",
        r"i recommend saying",
        r"you could say",
        r"just a suggestion",
        r"next question"  # user-triggered
    ]

    final_cleaned_log = []
    for entry in evaluation_log:
        q = entry.get("question", "").strip().lower()

        # skip if matches ANY strict filler pattern
        if any(re.search(p, q) for p in strict_filler_patterns):
            continue

        # skip questions that start with "It's great", "I couldn't", "Your response", etc.
        if re.match(r"(it's|i couldn't|your response|your answer|small correction|note that)", q):
            continue

        # skip questions less than 6 words (high chance of being filler)
        if len(q.split()) < 4:
            continue

        # skip generic greetings / politeness
        if any(q.startswith(x) for x in ["hi", "hello", "okay", "alright", "sure"]):
            continue

        final_cleaned_log.append(entry)

    evaluation_log = final_cleaned_log


    # Determine HR or Technical questions
    is_technical = interview_type.lower() == "technical"
    is_hr = interview_type.lower() == "hr"

    hr_questions = [] if is_technical else [q for q in evaluation_log if "behavior" in q.get("question","").lower() or "team" in q.get("question","").lower()]
    tech_questions = [] if is_hr else [q for q in evaluation_log if q not in hr_questions]

    # Correct common technical terms spelling in answers
    def correct_spelling(text):
        corrections = {
            r"\bhtml\b": "HTML",
            r"\bcss\b": "CSS",
            r"\bjavascript\b": "JavaScript",
            r"\breact\b": "React",
            r"\bnode\.js\b": "Node.js",
            r"\bpython\b": "Python",
            r"\bmern\b": "MERN"
        }
        for pattern, repl in corrections.items():
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        return text

    def section_summary(entries, section_name):
        if not entries:
            return f"{section_name}:\nNo questions answered.\n"

        summary_lines = [f"{section_name}:"]
        strengths = set()
        weaknesses = set()
        total_score = 0

        for i, entry in enumerate(entries, 1):
            q = correct_spelling(entry.get("question", "N/A"))
            a = correct_spelling(entry.get("answer", "N/A"))
            relevance = entry.get("relevance", 0)
            technical = entry.get("technical_correctness", 0)
            clarity = entry.get("clarity", 0)
            avg_score = round((relevance + technical + clarity)/3, 2)
            total_score += avg_score

            comment = entry.get("comment","") if i > 1 else ""

            summary_lines.append(f"Q{i}: {q}\nA{i}: {a}\n{'Comment: '+comment if comment else ''}\nScore: {avg_score}/5\n")

            if technical >= 4:
                strengths.add("Technical Knowledge")
            if relevance >= 4:
                strengths.add("Answer Relevance")
            if clarity >= 4:
                strengths.add("Communication Clarity")

            if relevance < 3:
                weaknesses.add("Relevance")
            if technical < 3:
                weaknesses.add("Technical Correctness")
            if clarity < 3:
                weaknesses.add("Clarity")
    # Group questions by round name
    rounds_order = ["Aptitude Assesment", "Technical Evaluation", "Behavioral/HR Round"]
    grouped_data = {}
    for entry in evaluation_log:
        r_name = entry.get("round_name", "General")
        if r_name not in grouped_data:
            grouped_data[r_name] = []
        
        grouped_data[r_name].append({
            "question": correct_spelling(entry.get("question", "")),
            "answer": correct_spelling(entry.get("answer", "")),
            "comment": entry.get("comment", ""),
            "score": round((entry.get("relevance",0)+entry.get("technical_correctness",0)+entry.get("clarity",0))/3,2)
        })

    # Sort grouped data by the logical order
    sorted_rounds = []
    for r_title in rounds_order:
        if r_title in grouped_data:
            sorted_rounds.append({"name": r_title, "items": grouped_data[r_title]})
    
    # Add any other rounds that might exist but aren't in the predefined order
    for r_title, items in grouped_data.items():
        if not any(sr["name"] == r_title for sr in sorted_rounds):
            sorted_rounds.append({"name": r_title, "items": items})

    # Overall Performance
    overall_score = round(sum((q.get("relevance",0)+q.get("technical_correctness",0)+q.get("clarity",0))/3 for q in evaluation_log)/len(evaluation_log),2) if evaluation_log else 0
    rating_stars = "⭐"*round(overall_score) + "☆"*(5-round(overall_score))
    
    # AI-generated overall summary
    try:
        prompt = f"Summarize the candidate's interview performance from this log:\n{json.dumps(evaluation_log, indent=2)}\nHighlight strengths, weaknesses, and engagement concisely."
        overall_summary = generator(prompt, max_tokens=200)
        rec_prompt = f"""
        Based on the following interview evaluation log, generate exactly 3 to 4 short, 
        actionable recommendations for the candidate.
        Evaluation Log:
        {json.dumps(evaluation_log, indent=2)}
        """
        llm_recommendations = generator(rec_prompt, max_tokens=250)
    except Exception:
        overall_summary = "Could not generate AI summary."
        llm_recommendations = "Could not generate AI recommendations."

    def extract_feedback_sections(text):
        strengths_match = re.search(r"Strengths:\s*(.*?)(?=\n\s*\*\*Weaknesses|\nWeaknesses:|\Z)", text, flags=re.S|re.I)
        weaknesses_match = re.search(r"Weaknesses:\s*(.*?)(?=\n\s*\*\*Engagement|\nEngagement:|\Z)", text, flags=re.S|re.I)
        engagement_match = re.search(r"Engagement:\s*(.*)", text, flags=re.S|re.I)

        def clean(s):
            s = s.strip()
            s = re.sub(r"^[\*\s]+", "", s)
            s = re.sub(r"[-•]\s*", "", s)
            s = re.sub(r"\s+", " ", s)
            return s.strip()

        if not strengths_match and not weaknesses_match and not engagement_match:
            return {"overall_summary": clean(text)}

        return {
            "strengths": clean(strengths_match.group(1)) if strengths_match else "",
            "weaknesses": clean(weaknesses_match.group(1)) if weaknesses_match else "",
            "engagement": clean(engagement_match.group(1)) if engagement_match else ""
        }

    return {
        "candidate_details": {
            "name": candidate_name,
            "interview_mode": interview_type.capitalize(),
            "difficulty_level": level.capitalize(),
            "date_time": now
        },
        "interview_summary": {
            "summary_text": extract_feedback_sections(overall_summary.strip()),
            "total_questions": len(evaluation_log)
        },
        "grouped_rounds": sorted_rounds,
        "overall": {
            "average_score": overall_score,
            "rating": rating_stars
        },
        ### CHANGE 3 — FIXED VERSION
        "recommendations": [
            line.strip("-• ").strip()
            for line in llm_recommendations.split("\n")
            if line.strip() and not line.startswith("Based on")
        ],


        "evaluation_log": evaluation_log
    }
