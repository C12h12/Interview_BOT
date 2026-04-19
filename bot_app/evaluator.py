import re, json
from .config import generator

def evaluate_answer(answer, question):
    eval_prompt = f"""
You are an interview evaluator. ONLY respond with a valid JSON object, like this:
{{
  "relevance": <0-5>,
  "technical_correctness": <0-5>,
  "clarity": <0-5>,
  "comment": "<feedback>"
}}

Evaluate the following candidate answer:

Question: {question}
Answer: {answer}

Do NOT include any text outside the JSON.
"""
    try:
        eval_result = generator(eval_prompt, max_tokens=300, temperature=0.7)  # now a string
        # Extract JSON from the string
        json_matches = re.findall(r"\{.*?\}", eval_result, re.DOTALL)
        json_str = json_matches[-1] if json_matches else None

        if json_str:
            try:
                parsed = json.loads(json_str)
                return {
                    "relevance": parsed.get("relevance", 0),
                    "technical_correctness": parsed.get("technical_correctness", 0),
                    "clarity": parsed.get("clarity", 0),
                    "comment": parsed.get("comment", "No feedback provided.")
                }
            except json.JSONDecodeError:
                return {
                    "relevance": 0,
                    "technical_correctness": 0,
                    "clarity": 0,
                    "comment": f"Invalid JSON from model: {eval_result}"
                }
        else:
            return {
                "relevance": 0,
                "technical_correctness": 0,
                "clarity": 0,
                "comment": f"No JSON found in response: {eval_result}"
            }
    except Exception as e:
        return {
            "relevance": 0,
            "technical_correctness": 0,
            "clarity": 0,
            "comment": f"Error: {e}"
        }
