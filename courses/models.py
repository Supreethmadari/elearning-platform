from django.db import models
from django.conf import settings
from django.utils import timezone
from accounts.models import User
import uuid


class Course(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    
    price = models.IntegerField() 
    rating = models.DecimalField(max_digits=3, decimal_places=1, default=5.0)
    trainer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="courses")

    # Tier 1: Live Virtual
    live_virtual_old_price = models.IntegerField(default=0)
    live_virtual_new_price = models.IntegerField(default=0)
    
    # Tier 2: Blended
    blended_old_price = models.IntegerField(default=0)
    blended_new_price = models.IntegerField(default=0)
    
    # Tier 3: Classroom
    classroom_old_price = models.IntegerField(default=0)
    classroom_new_price = models.IntegerField(default=0)
    # --------------------------------------------------------

    def get_live_discount(self):
        if self.live_virtual_old_price > 0:
            percentage = ((self.live_virtual_old_price - self.live_virtual_new_price) / self.live_virtual_old_price) * 100
            return int(percentage)
        return 0

    def get_blended_discount(self):
        if self.blended_old_price > 0:
            percentage = ((self.blended_old_price - self.blended_new_price) / self.blended_old_price) * 100
            return int(percentage)
        return 0
    
    def get_classroom_discount(self):
        if self.classroom_old_price > 0:
            percentage = ((self.classroom_old_price - self.classroom_new_price) / self.classroom_old_price) * 100
            return int(percentage)
        return 0

    def __str__(self):
        return self.title

    def progress_for(self, student):
        total = self.lessons.count()
        if total == 0:
            return 0
        completed = LessonProgress.objects.filter(
            student=student,
            lesson__course=self,
            completed=True
        ).count()
        return int((completed / total) * 100)


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
    watched_seconds = models.IntegerField(default=0)

    class Meta:
        unique_together = ['student', 'lesson']


class Enrollment(models.Model):
    ENROLLMENT_STATUS_CHOICES = [
        ('PENDING_PAYMENT', 'Pending Payment'),
        ('PENDING_VERIFICATION', 'Pending Verification'),
        ('ACTIVE', 'Active'),
        ('REJECTED', 'Rejected'),
        ('COMPLETED', 'Completed'),
    ]

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="enrollments")
    tier = models.CharField(max_length=50, default='Live Virtual', blank=True)
    status = models.CharField(max_length=30, choices=ENROLLMENT_STATUS_CHOICES, default='ACTIVE')
    completed = models.BooleanField(default=False)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student.username} - {self.course.title} ({self.status})"


class Payment(models.Model):
    PAYMENT_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PENDING_VERIFICATION', 'Pending Verification'),
        ('PARTIALLY_PAID', 'Partially Paid'),
        ('PAID', 'Paid'),
        ('REJECTED', 'Rejected'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('ONLINE', 'Online Payment'),
        ('UPI', 'UPI Transfer'),
        ('BANK_TRANSFER', 'Bank Transfer (NEFT/IMPS)'),
        ('CASH', 'Cash'),
        ('CHEQUE', 'Cheque'),
        ('OTHER', 'Other'),
    ]

    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name='payment', null=True, blank=True)
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='payments')
    tier = models.CharField(max_length=50, default='Live Virtual', blank=True)

    course_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    claimed_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    verified_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    remaining_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)

    payment_method = models.CharField(max_length=30, choices=PAYMENT_METHOD_CHOICES, default='ONLINE')
    payment_date = models.DateField(default=timezone.now)
    payment_reference = models.CharField(max_length=100, blank=True, null=True)
    student_notes = models.TextField(blank=True, null=True)

    status = models.CharField(max_length=30, choices=PAYMENT_STATUS_CHOICES, default='PENDING')

    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_payments')
    verified_at = models.DateTimeField(null=True, blank=True)
    admin_notes = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment #{self.id} - {self.student.username} - {self.course.title} ({self.status})"


class StudentProgress(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    completed_lessons = models.IntegerField(default=0)
    total_lessons = models.IntegerField(default=0)
    hours_spent = models.FloatField(default=0)
    is_completed = models.BooleanField(default=False)

    def update_status(self):
        if self.total_lessons > 0 and self.completed_lessons >= self.total_lessons:
            self.is_completed = True
            self.save()



class SupportQuery(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='queries')
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    answer = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Query from {self.student.username}"


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
    

class StudentCertificate(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    certificate_id = models.CharField(max_length=50, unique=True, blank=True)
    pdf = models.FileField(upload_to="certificates/", null=True, blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.certificate_id:
            self.certificate_id = "CYNO-" + uuid.uuid4().hex[:10].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.username} - {self.course.title}"
    

