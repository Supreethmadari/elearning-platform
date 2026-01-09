from django.db import models
from django.conf import settings
from accounts.models import User # Ensure this points to your actual custom User app

class Course(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    price = models.IntegerField()
    # Adding a rating field to support the "Course Rating" card in your trainer dashboard
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=5.0)
    trainer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="courses")

    def __str__(self):
        return self.title

class Lesson(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=200)
    video = models.FileField(upload_to="lesson_videos/", blank=True, null=True)
    notes = models.FileField(upload_to="lesson_notes/", blank=True, null=True)
    order = models.IntegerField()

    def __str__(self):
        return self.title

class LessonProgress(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE)
    completed = models.BooleanField(default=False)

    class Meta:
        unique_together = ['student', 'lesson']

class Enrollment(models.Model):
    
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.student.username} - {self.course.title}"
    
class SupportQuery(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='queries')
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    answer = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Query from {self.student.username}"
    
class StudentProgress(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    completed_lessons = models.IntegerField(default=0)
    total_lessons = models.IntegerField(default=0)
    hours_spent = models.FloatField(default=0)
    is_completed = models.BooleanField(default=False)


# models.py
class LiveClass(models.Model):
    title = models.CharField(max_length=200)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    trainer = models.ForeignKey(User, on_delete=models.CASCADE)

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    zoom_meeting_id = models.CharField(max_length=100)
    zoom_join_url = models.TextField()
    zoom_start_url = models.URLField(blank=True, null=True)

    is_active = models.BooleanField(default=True)

    def is_live(self):
        now = timezone.now()
        return self.start_time <= now <= self.end_time

