from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def ask_ai(question):
    response = client.responses.create(
        model="gpt-4.1-mini",
        input=question
    )
    return response.output_text.strip()
