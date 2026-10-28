import os
import json
import logging
from django.shortcuts import render
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from courses.models import Course, Lesson, Enrollment, SupportQuery
from .models import AIChatMessage
from .ai_engine import ask_ai, stream_ask_ai, generate_lesson_quiz, extract_notes_text

logger = logging.getLogger(__name__)


def get_student_context(request):
    """
    Builds personalized student context:
    - Name & username
    - Enrolled courses & progress
    - Current lesson / course context
    - Study notes extracted text
    """
    if not request.user.is_authenticated:
        return None

    user = request.user
    student_name = user.first_name.strip() if user.first_name else user.username

    # Active enrolled courses
    enrollments = Enrollment.objects.filter(
        student=user,
        status='ACTIVE'
    ).select_related('course')

    enrolled_courses = []
    for enr in enrollments:
        enrolled_courses.append({
            "id": enr.course.id,
            "title": enr.course.title,
            "progress": enr.course.progress_for(user)
        })

    # Active course / lesson (from params or session)
    course_id = request.GET.get("course_id") or request.POST.get("course_id") or request.session.get("current_course_id")
    lesson_id = request.GET.get("lesson_id") or request.POST.get("lesson_id") or request.session.get("current_lesson_id")

    current_course_title = None
    current_lesson_title = None
    notes_text = None
    lesson_obj = None
    course_obj = None

    if lesson_id:
        try:
            lesson_obj = Lesson.objects.select_related('course').get(id=lesson_id)
            current_lesson_title = lesson_obj.title
            current_course_title = lesson_obj.course.title
            course_obj = lesson_obj.course
            if lesson_obj.notes and hasattr(lesson_obj.notes, 'path') and os.path.exists(lesson_obj.notes.path):
                notes_text = extract_notes_text(lesson_obj.notes.path)
        except Exception as e:
            logger.debug(f"Could not load lesson {lesson_id} context: {e}")
    elif course_id:
        try:
            course_obj = Course.objects.get(id=course_id)
            current_course_title = course_obj.title
        except Exception as e:
            logger.debug(f"Could not load course {course_id} context: {e}")
    elif enrolled_courses:
        current_course_title = enrolled_courses[0]["title"]

    return {
        "student_name": student_name,
        "enrolled_courses": enrolled_courses,
        "current_course": current_course_title,
        "current_lesson": current_lesson_title,
        "notes_text": notes_text,
        "course_obj": course_obj,
        "lesson_obj": lesson_obj,
    }


def chat(request):
    """
    Standard JSON endpoint with multi-turn conversation memory, context grounding,
    and persistent database history.
    """
    try:
        msg = request.GET.get("msg") or request.POST.get("msg")
        if not msg:
            return JsonResponse({"reply": "Please ask a question."})

        # Retrieve session chat history (Multi-turn memory)
        history = request.session.get("ai_chat_history", [])

        # Gather rich student & course context
        student_context = get_student_context(request)

        # Generate response using context & history
        answer = ask_ai(msg, history=history, student_context=student_context)

        # Update multi-turn session history (keep last 10 turns)
        history.append({"role": "user", "content": str(msg).strip()})
        history.append({"role": "assistant", "content": str(answer).strip()})
        request.session["ai_chat_history"] = history[-10:]
        request.session.modified = True

        # Persistent storage in database for logged in students
        if request.user.is_authenticated:
            course_obj = student_context.get("course_obj") if student_context else None
            lesson_obj = student_context.get("lesson_obj") if student_context else None
            AIChatMessage.objects.create(
                user=request.user,
                course=course_obj,
                lesson=lesson_obj,
                role='user',
                content=str(msg).strip()
            )
            AIChatMessage.objects.create(
                user=request.user,
                course=course_obj,
                lesson=lesson_obj,
                role='assistant',
                content=str(answer).strip()
            )

        return JsonResponse({
            "reply": answer,
            "student_name": student_context.get("student_name") if student_context else None,
            "current_course": student_context.get("current_course") if student_context else None,
            "current_lesson": student_context.get("current_lesson") if student_context else None,
            "has_history": len(request.session["ai_chat_history"]) > 2
        })
    except Exception as e:
        logger.error(f"Chat view error: {e}")
        return JsonResponse({"reply": "AI error: " + str(e)})


def stream_chat(request):
    """
    Server-Sent Events (SSE) streaming endpoint: streams tokens live as they generate.
    Also saves conversation turns to persistent database storage upon completion.
    """
    msg = request.GET.get("msg") or request.POST.get("msg")
    if not msg:
        return JsonResponse({"error": "No question provided"}, status=400)

    history = request.session.get("ai_chat_history", [])
    student_context = get_student_context(request)

    def event_stream():
        full_reply = []
        try:
            for chunk in stream_ask_ai(msg, history=history, student_context=student_context):
                full_reply.append(chunk)
                payload = json.dumps({"token": chunk})
                yield f"data: {payload}\n\n"

            combined_reply = "".join(full_reply).strip()

            # Update session history
            history.append({"role": "user", "content": str(msg).strip()})
            history.append({"role": "assistant", "content": combined_reply})
            request.session["ai_chat_history"] = history[-10:]
            request.session.modified = True

            # Persistent DB save
            if request.user.is_authenticated:
                course_obj = student_context.get("course_obj") if student_context else None
                lesson_obj = student_context.get("lesson_obj") if student_context else None
                try:
                    AIChatMessage.objects.create(
                        user=request.user,
                        course=course_obj,
                        lesson=lesson_obj,
                        role='user',
                        content=str(msg).strip()
                    )
                    AIChatMessage.objects.create(
                        user=request.user,
                        course=course_obj,
                        lesson=lesson_obj,
                        role='assistant',
                        content=combined_reply
                    )
                except Exception as save_err:
                    logger.error(f"Could not persist chat message: {save_err}")

            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error(f"Streaming generator error: {e}")
            err_payload = json.dumps({"error": str(e)})
            yield f"data: {err_payload}\n\n"
            yield "data: [DONE]\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


def get_history(request):
    """
    Retrieves previous persistent chat messages for the current user and context.
    """
    if not request.user.is_authenticated:
        history = request.session.get("ai_chat_history", [])
        return JsonResponse({"messages": history})

    course_id = request.GET.get("course_id")
    lesson_id = request.GET.get("lesson_id")

    qs = AIChatMessage.objects.filter(user=request.user)
    if lesson_id:
        qs = qs.filter(lesson_id=lesson_id)
    elif course_id:
        qs = qs.filter(course_id=course_id)

    # Return last 30 messages
    messages = []
    for m in qs.order_by('-created_at')[:30][::-1]:
        messages.append({
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "timestamp": m.created_at.strftime("%I:%M %p")
        })

    return JsonResponse({"messages": messages})


def get_quiz(request):
    """
    Generates an interactive mini-quiz for the active lesson context.
    """
    student_context = get_student_context(request)
    quiz_data = generate_lesson_quiz(student_context)
    return JsonResponse(quiz_data)


@csrf_exempt
def clear_chat(request):
    """
    Resets both the session memory and persistent messages for current context.
    """
    request.session["ai_chat_history"] = []
    request.session.modified = True

    if request.user.is_authenticated:
        lesson_id = request.GET.get("lesson_id") or request.POST.get("lesson_id")
        course_id = request.GET.get("course_id") or request.POST.get("course_id")
        qs = AIChatMessage.objects.filter(user=request.user)
        if lesson_id:
            qs.filter(lesson_id=lesson_id).delete()
        elif course_id:
            qs.filter(course_id=course_id).delete()
        else:
            qs.delete()

    return JsonResponse({"status": "cleared", "message": "Conversation history reset successfully."})


@csrf_exempt
def escalate_to_mentor(request):
    """
    Converts a query into a SupportQuery doubt ticket for the human trainer (Level 4 Handoff).
    """
    if not request.user.is_authenticated:
        return JsonResponse({"status": "error", "message": "Please log in to contact your trainer."}, status=401)

    question = request.POST.get("question") or request.GET.get("question")
    if not question:
        history = request.session.get("ai_chat_history", [])
        user_msgs = [m["content"] for m in history if m.get("role") == "user"]
        question = user_msgs[-1] if user_msgs else "Student requested trainer help from CYANOPY Tutor."

    query = SupportQuery.objects.create(
        student=request.user,
        message=f"[Escalated from AI Tutor] {question.strip()}"
    )

    return JsonResponse({
        "status": "success",
        "query_id": query.id,
        "message": "Your doubt has been submitted directly to your trainer! They will review and answer it shortly."
    })
