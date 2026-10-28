import os
import json
import logging
from openai import OpenAI
from django.conf import settings

logger = logging.getLogger(__name__)


def get_client_and_model():
    """
    Returns (client, model_name) based on configured keys:
    1. If GROQ_API_KEY is present, uses Groq (100% Free, high-speed OpenAI-compatible).
    2. If OPENAI_API_KEY starts with 'gsk_', auto-routes to Groq.
    3. If standard OPENAI_API_KEY is present, uses OpenAI gpt-4o-mini.
    """
    openai_key = os.getenv("OPENAI_API_KEY") or getattr(settings, "OPENAI_API_KEY", None)
    groq_key = os.getenv("GROQ_API_KEY") or getattr(settings, "GROQ_API_KEY", None)

    # 1. Dedicated Groq Key (100% Free at console.groq.com)
    if groq_key:
        client = OpenAI(
            api_key=groq_key,
            base_url="https://api.groq.com/openai/v1"
        )
        return client, "qwen/qwen3.8-27b"

    # 2. In case user pasted a Groq key into OPENAI_API_KEY (starts with 'gsk_')
    if openai_key and openai_key.startswith("gsk_"):
        client = OpenAI(
            api_key=openai_key,
            base_url="https://api.groq.com/openai/v1"
        )
        return client, "qwen/qwen3.8-27b"

    # 3. Standard OpenAI Key
    if openai_key:
        client = OpenAI(api_key=openai_key)
        return client, "gpt-4o-mini"

    return None, None


def extract_notes_text(notes_file_path, max_chars=1800):
    """Extracts text from lesson PDF notes to ground the AI answers."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(notes_file_path)
        extracted = []
        for page in reader.pages[:4]:
            t = page.extract_text()
            if t:
                extracted.append(t)
        full_text = "\n".join(extracted).strip()
        if len(full_text) > max_chars:
            return full_text[:max_chars] + "\n... [Remaining notes truncated for brevity]"
        return full_text
    except Exception as e:
        logger.warning(f"Could not extract notes text from {notes_file_path}: {e}")
        return ""


def build_system_prompt(student_context=None):
    """Constructs a personalized, context-aware prompt grounded in student data."""
    base_prompt = (
        "You are CYANOPY Tutor, a smart, friendly, and encouraging personal AI educational mentor "
        "on the CYANOPY Learning Platform.\n"
        "Your purpose:\n"
        "1. Teach and explain programming, computer science, data structures, algorithms, and technology concepts clearly.\n"
        "2. Provide step-by-step explanations, helpful code snippets (in Python, Java, C++, JavaScript, SQL, etc.), and intuitive analogies.\n"
        "3. Converse like a real human tutor: warm, encouraging, concise, and focused. Avoid overly rigid boilerplate.\n"
        "4. Remember the context of previous messages in this conversation so follow-up questions are answered naturally.\n"
        "5. If asked about platform features:\n"
        "   - Students watch video lessons in 'My Learning' or 'Continue Learning'.\n"
        "   - View or download attached PDF study notes with 'View Online' or 'Download Notes'.\n"
        "   - Join live classes when the trainer starts a live session.\n"
        "   - Ask doubts to their trainer using 'Connect with Mentor' or the 'Ask Human Mentor' button."
    )

    if not student_context:
        return base_prompt

    student_name = student_context.get("student_name")
    enrolled_courses = student_context.get("enrolled_courses", [])
    current_course = student_context.get("current_course")
    current_lesson = student_context.get("current_lesson")
    notes_text = student_context.get("notes_text")

    context_lines = ["\n--- CURRENT STUDENT & PLATFORM CONTEXT ---"]
    if student_name:
        context_lines.append(f"- Student Name: {student_name} (Address the student naturally by name when greeting or providing personalized guidance).")
    if enrolled_courses:
        courses_str = ", ".join([f"{c.get('title')} ({c.get('progress', 0)}% done)" for c in enrolled_courses])
        context_lines.append(f"- Enrolled Courses: {courses_str}")
    if current_course:
        context_lines.append(f"- Active Course: {current_course}")
    if current_lesson:
        context_lines.append(f"- Active Lesson Being Studied: {current_lesson}")
    if notes_text:
        context_lines.append(f"- Lesson Study Notes Excerpt:\n\"\"\"\n{notes_text}\n\"\"\"\n(Reference or explain these notes directly when the student asks about the current topic).")

    context_lines.append(
        "Guidelines:\n"
        "- Tailor your examples to the student's enrolled subjects.\n"
        "- When writing code, format inside markdown code blocks with language identifiers (e.g. ```python).\n"
        "- If a student asks follow-up questions (like 'give me an example of the second one' or 'explain line 3'), use chat history to answer accurately.\n"
        "- If a student requires personal grading, payment help, or manual trainer intervention, remind them they can click 'Ask Human Mentor'."
    )

    return base_prompt + "\n" + "\n".join(context_lines)


def assemble_messages(question, history=None, student_context=None):
    """Assembles prompt and chat turns for the model."""
    system_prompt = build_system_prompt(student_context)
    messages = [{"role": "system", "content": system_prompt}]

    if history and isinstance(history, list):
        for item in history[-8:]:
            role = item.get("role")
            content = item.get("content")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": str(content).strip()})

    messages.append({"role": "user", "content": str(question).strip()})
    return messages


def ask_ai(question, history=None, student_context=None):
    """
    Generates interactive AI response with multi-turn memory and student context awareness.
    """
    if not question or not str(question).strip():
        return "Please ask a question, and I'll be glad to help!"

    client, model = get_client_and_model()

    if client is None:
        return (
            "👋 Hi there! I am **CYANOPY Tutor**.\n\n"
            "To activate live AI responses, please configure your **FREE API Key** (e.g. from GroqCloud or OpenAI) in your `.env` or `settings.py` file.\n\n"
            "Need help with a course topic right away? You can also reach out to your instructor via the **Connect with Mentor** button!"
        )

    messages = assemble_messages(question, history=history, student_context=student_context)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=850,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"AI generation error: {e}")
        return f"Sorry, I encountered an issue connecting to the AI service: {str(e)}"


def stream_ask_ai(question, history=None, student_context=None):
    """
    Yields chunks of text in real-time as tokens are generated.
    """
    if not question or not str(question).strip():
        yield "Please ask a question, and I'll be glad to help!"
        return

    client, model = get_client_and_model()

    if client is None:
        fallback = (
            "👋 Hi there! I am **CYANOPY Tutor**.\n\n"
            "To activate live AI responses, please configure your **FREE API Key** in your `.env` file."
        )
        for word in fallback.split(" "):
            yield word + " "
        return

    messages = assemble_messages(question, history=history, student_context=student_context)

    try:
        response_stream = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=850,
            temperature=0.7,
            stream=True
        )
        for chunk in response_stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield f"Error streaming AI response: {str(e)}"


def generate_lesson_quiz(student_context=None):
    """
    Generates a 3-question multiple choice quiz with explanations based on current lesson context.
    Returns a dict with questions or fallback questions.
    """
    lesson_title = (student_context.get("current_lesson") if student_context else None) or "Key Programming Concepts"
    course_title = (student_context.get("current_course") if student_context else None) or "General Programming"
    notes_text = (student_context.get("notes_text") if student_context else None) or ""

    client, model = get_client_and_model()

    if client is None:
        # High quality fallback quiz if API key is not yet set
        return {
            "title": f"Practice Quiz: {lesson_title}",
            "questions": [
                {
                    "question": f"In {lesson_title}, what is the primary best practice?",
                    "options": [
                        "A) Write clean, modular, and readable code",
                        "B) Ignore testing and comments",
                        "C) Put all code in a single global variable",
                        "D) Avoid using standard documentation"
                    ],
                    "correct_index": 0,
                    "explanation": "Writing clean, modular code makes debugging, maintenance, and collaboration efficient."
                },
                {
                    "question": "Which data structure provides O(1) average lookup time?",
                    "options": [
                        "A) Singly Linked List",
                        "B) Hash Table / Dictionary",
                        "C) Linear Array (Unsorted)",
                        "D) Binary Search Tree (Unbalanced)"
                    ],
                    "correct_index": 1,
                    "explanation": "Hash Tables use key hashing to achieve O(1) constant average lookup time."
                },
                {
                    "question": "What is the recommended approach when handling unexpected exceptions?",
                    "options": [
                        "A) Suppress all errors silently",
                        "B) Catch specific exceptions and log helpful messages",
                        "C) Let the server crash completely",
                        "D) Delete the file that threw the error"
                    ],
                    "correct_index": 1,
                    "explanation": "Catching specific exceptions prevents unwanted side-effects and logs actionable debugging information."
                }
            ]
        }

    quiz_prompt = (
        f"You are creating a quick 3-question interactive multiple-choice quiz for a student learning '{lesson_title}' in the course '{course_title}'.\n"
    )
    if notes_text:
        quiz_prompt += f"Here is an excerpt of their study notes:\n\"\"\"\n{notes_text}\n\"\"\"\n"

    quiz_prompt += (
        "Generate exactly 3 relevant, engaging multiple choice questions based on the topic and notes.\n"
        "Respond ONLY with a valid JSON object in this exact schema (no markdown formatting, no code fences, just raw JSON):\n"
        "{\n"
        '  "title": "Practice Quiz: ' + lesson_title + '",\n'
        '  "questions": [\n'
        '    {\n'
        '      "question": "Clear question text?",\n'
        '      "options": ["A) ...", "B) ...", "C) ...", "D) ..."],\n'
        '      "correct_index": 0,\n'
        '      "explanation": "Why this answer is correct."\n'
        '    }\n'
        '  ]\n'
        "}"
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a professional quiz generator. Output ONLY valid JSON."},
                {"role": "user", "content": quiz_prompt}
            ],
            max_tokens=800,
            temperature=0.4
        )
        raw = response.choices[0].message.content.strip()
        # Clean potential code markdown fences
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        data = json.loads(raw.strip())
        return data
    except Exception as e:
        logger.error(f"Quiz generation error: {e}")
        # Return fallback quiz
        return {
            "title": f"Practice Quiz: {lesson_title}",
            "questions": [
                {
                    "question": f"What is a core concept covered in {lesson_title}?",
                    "options": [
                        "A) Understanding data flow and structured logic",
                        "B) Hardcoding fixed values everywhere",
                        "C) Ignoring error states",
                        "D) Skipping documentation"
                    ],
                    "correct_index": 0,
                    "explanation": "Understanding structured data flow is essential to mastering programming concepts."
                },
                {
                    "question": "Why is regular practice and quiz review important in coding?",
                    "options": [
                        "A) It reinforces active recall and identifies knowledge gaps",
                        "B) It slows down overall learning",
                        "C) It prevents learning new frameworks",
                        "D) It only helps with exams, not projects"
                    ],
                    "correct_index": 0,
                    "explanation": "Active recall through quizzes significantly strengthens retention and long-term problem-solving skills."
                }
            ]
        }