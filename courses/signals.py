from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db.models import Sum
from .models import LessonProgress, StudentProgress

@receiver(post_save, sender=LessonProgress)
def update_student_progress(sender, instance, **kwargs):
    course = instance.lesson.course
    student = instance.student

    total = course.lessons.count()
    completed = LessonProgress.objects.filter(
        student=student,
        lesson__course=course,
        completed=True
    ).count()

    watched = LessonProgress.objects.filter(
        student=student,
        lesson__course=course
    ).aggregate(total=Sum('watched_seconds'))['total'] or 0

    obj, _ = StudentProgress.objects.get_or_create(student=student, course=course)
    obj.completed_lessons = completed
    obj.total_lessons = total
    obj.hours_spent = watched
    obj.is_completed = (completed == total and total != 0)
    obj.save()
