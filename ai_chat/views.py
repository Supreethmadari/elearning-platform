from django.shortcuts import render

from django.http import JsonResponse
from .ai_engine import ask_ai

def chat(request):
    try:
        msg = request.GET.get("msg")
        if not msg:
            return JsonResponse({"reply": "Please ask a question."})
        answer = ask_ai(msg)
        return JsonResponse({"reply": answer})
    except Exception as e:
        return JsonResponse({"reply": "AI error: " + str(e)})

