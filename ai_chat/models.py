from django.db import models
from django.contrib.auth import get_user_model
from courses.models import Course, Lesson

User = get_user_model()


class AIChatMessage(models.Model):
    ROLE_CHOICES = (
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ai_messages')
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_messages')
    lesson = models.ForeignKey(Lesson, on_delete=models.SET_NULL, null=True, blank=True, related_name='ai_messages')
    role = models.CharField(max_length=15, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.user.username} - {self.role}: {self.content[:40]}"
