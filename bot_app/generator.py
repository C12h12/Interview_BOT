import re
from .config import generator

def generate_next_question(history: str):
    try:
        response = generator(history)  # Only API call
    except Exception as e:
        return f"Error calling generator: {e}"

    # --- Normalize Mistral API output ---
    generated_text = None

    if isinstance(response, dict):
        if "choices" in response and len(response["choices"]) > 0:
            generated_text = response["choices"][0]["message"]["content"]
        else:
            generated_text = str(response)
    else:
        generated_text = str(response)

    # --- Postprocess ---
    new_part = generated_text.replace(history, "").strip()
    new_part = re.sub(r'^\**\s*Interviewer:\**\s*', "", new_part, flags=re.IGNORECASE)

    # First line only
    match = re.search(r'^(.*?)(?:\n|$)', new_part)
    return match.group(1).strip() if match else None

def extract_name_from_resume(resume_text: str):
    """
    Extracts the candidate's full name from the resume text using the AI.
    """
    prompt = f"""
    Extract ONLY the full name of the candidate from the following resume text. 
    If you cannot find a clear name, return 'Candidate'.
    Output only the name and nothing else.
    ==================================================================
    RESUME TEXT:
    {resume_text[:2000]} 
    ==================================================================
    NAME:"""
    
    try:
        response = generator(prompt)
        # Postprocess same as generator logic
        if isinstance(response, dict):
            name = response["choices"][0]["message"]["content"].strip()
        else:
            name = str(response).strip()
        
        # Clean up any "Name: " prefix
        name = re.sub(r'^(Name|Candidate Name):\s*', "", name, flags=re.IGNORECASE)
        return name if name else "Candidate"
    except Exception as e:
        print(f"Name Extraction Error: {e}")
        return "Candidate"