import os
import requests
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
API_KEY = os.getenv("OPENAI_API_KEY")

MAX_RETRIES = 5
BASE_DELAY = 2  # seconds

# Safety check
if not API_KEY or not API_KEY.startswith("sk-proj-"):
    raise Exception("No valid OpenAI project API key found in OPENAI_API_KEY.")

def generator(prompt, max_tokens=150, temperature=0.7):
    """Generate a response using OpenAI GPT-4o-mini with a project key."""
    api_url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL_NAME,
        "messages": [
            #{"role": "system", "content": "You are an AI Interview Preparation Assistant. Your role is to simulate a professional interview for the candidate, using the provided job description and resume. You must ask relevant, context-aware questions and give constructive feedback."},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(api_url, headers=headers, json=data)

            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]

            elif response.status_code in [429, 503]:
                delay = BASE_DELAY * (2 ** attempt)
                print(f"{response.status_code} - Retrying in {delay} seconds...")
                time.sleep(delay)

            else:
                print(f"Error {response.status_code}: {response.text}")
                break

        except requests.exceptions.RequestException as e:
            delay = BASE_DELAY * (2 ** attempt)
            print(f"Network error: {e}. Retrying in {delay} seconds...")
            time.sleep(delay)

    raise Exception("All retries failed to generate content.")

# Tokenizer placeholder
tokenizer = None

# Level durations for interviews
LEVEL_DURATIONS = {
    "easy": 10 * 60,
    "moderate": 20* 60,
    "experienced": 30 * 60
}
