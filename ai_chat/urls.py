from django.urls import path
from .views import chat, stream_chat, get_history, get_quiz, clear_chat, escalate_to_mentor

urlpatterns = [
    path("chat/", chat, name="ai_chat"),
    path("stream/", stream_chat, name="ai_stream"),
    path("history/", get_history, name="ai_history"),
    path("quiz/", get_quiz, name="ai_quiz"),
    path("clear/", clear_chat, name="ai_clear"),
    path("escalate/", escalate_to_mentor, name="ai_escalate"),
]
