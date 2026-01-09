from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.http import HttpResponseForbidden
from django.db.models import Count, Sum
from .models import Course, Lesson, Enrollment, LessonProgress, StudentProgress, LiveClass
from .models import SupportQuery
from django.utils import timezone
from .zoom_service import create_meeting



# ---------------- SECURE TRAINER DECORATOR ----------------
def trainer_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if not request.user.is_trainer:
            return HttpResponseForbidden("You are not authorized to access Trainer Portal.")
        return view_func(request, *args, **kwargs)
    return wrapper

# ---------------- LANDING ----------------
def landing(request):
    courses = Course.objects.all()[:6]
    return render(request, 'landing.html', {'courses': courses})


def home(request):
    return render(request, 'index.html')

def about(request):
    return render(request, 'about.html')

def contact(request):
    return render(request, 'contact.html')

def explore(request):
    return render(request, 'explore.html')



# ---------------- STUDENT DASHBOARD ----------------
@login_required(login_url='login')


@login_required
def student_dashboard(request):
    purchases = Enrollment.objects.filter(student=request.user)

    enrolled_courses_count = purchases.count()

    progress = StudentProgress.objects.filter(student=request.user)
    total_hours = progress.aggregate(total=Sum("hours_spent"))["total"] or 0
    certificates = progress.filter(is_completed=True).count()

    now = timezone.now()

    active_live = LiveClass.objects.filter(
        is_active=True,
        start_time__lte=now,
        end_time__gte=now
    )

    live_map = {l.course_id: l for l in active_live}

    enrolled_courses = []
    for p in purchases:
        enrolled_courses.append({
            "course": p.course,
            "live": live_map.get(p.course.id)
        })

    return render(request, "student_dashboard.html", {
        "enrolled_courses": enrolled_courses,   # for Live section
        "enrolled_courses_count": enrolled_courses_count,
        "learning_hours": round(total_hours, 1),
        "certificates": certificates,
        "progress": progress
    })





@login_required(login_url='login')
def purchase_course(request):
    courses = Course.objects.all()
    return render(request, "purchase.html", {"courses": courses})

@login_required
def my_courses(request):
    purchases = Enrollment.objects.filter(student=request.user)
    return render(request, "my_courses.html", {
        "purchases": purchases
    })

# ---------------- TRAINER DASHBOARD ----------------
@trainer_required
def trainer_dashboard(request):
    queries = SupportQuery.objects.filter(is_resolved=False).order_by('-created_at')
    resolved_queries = SupportQuery.objects.filter(is_resolved=True).order_by('-created_at')
    courses = Course.objects.filter(trainer=request.user)

    context = {
        'queries': queries,
        'resolved_queries': resolved_queries,
        'courses': courses,
    }
    return render(request, "trainer_dashboard.html", context)


@trainer_required
def create_course(request):
    if request.method == "POST":
        Course.objects.create(
            title=request.POST['title'],
            description=request.POST['description'],
            price=request.POST['price'],
            trainer=request.user
        )
        return redirect("trainer_dashboard")
    return render(request, "create_course.html")

@trainer_required
def trainer_courses(request):
    courses = Course.objects.filter(trainer=request.user)
    return render(request, "trainer_courses.html", {"courses": courses})


@trainer_required
def start_live_class(request):
    if request.method == "POST":

        title = request.POST.get("title")
        course_id = request.POST.get("course")
        duration = int(request.POST.get("duration"))

        zoom = create_meeting(title, duration)

        start = timezone.now()
        end = start + timezone.timedelta(minutes=duration)

        live = LiveClass.objects.create(
            trainer=request.user,
            course_id=course_id,
            title=title,
            zoom_meeting_id=str(zoom["id"]),
            zoom_join_url=zoom["join_url"],
            zoom_start_url=zoom["start_url"],
            start_time=start,
            end_time=end,
            is_active=True
        )

        return redirect(live.zoom_start_url)   # 🔴 OPEN ZOOM FOR TRAINER




# ---------------- COURSE DETAIL (SECURED) ----------------
@login_required
def course_detail(request, course_id):
    course = get_object_or_404(Course, id=course_id)

    is_trainer = request.user.is_trainer and course.trainer == request.user
    # Fixed: Uses Enrollment instead of Purchase
    is_purchased = Enrollment.objects.filter(student=request.user, course=course).exists()

    if not (is_trainer or is_purchased):
        return redirect("checkout", course_id=course.id)

    lessons = course.lessons.all()
    return render(request, "course_detail.html", {"course": course, "lessons": lessons})

# ---------------- ADD LESSON ----------------
@trainer_required
def add_lesson(request):
    courses = Course.objects.filter(trainer=request.user)

    if request.method == "POST":
        Lesson.objects.create(
            course_id=request.POST["course"],
            title=request.POST["title"],
            order=request.POST["order"],
            video=request.FILES["video"],
            notes=request.FILES.get("notes")
        )
        return redirect("trainer_dashboard")

    return render(request, "add_lesson.html", {"courses": courses})

# ---------------- PAYMENT & ENROLLMENT ----------------
@login_required
def checkout(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    return render(request, "payment_gateway.html", {"course": course})

@login_required
def payment_success(request, course_id):
    course = get_object_or_404(Course, id=course_id)

    # Fixed: Uses Enrollment and 'amount' field from your models.py
    Enrollment.objects.get_or_create(
        student=request.user,
        course=course,
        defaults={"amount": course.price}
    )

    return redirect("my_courses")

# ---------------- ANALYTICS ----------------
@trainer_required
def trainer_analytics(request):
    courses = Course.objects.filter(trainer=request.user)

    total_courses = courses.count()

    # Fixed: Uses Enrollment
    total_students = Enrollment.objects.filter(
        course__trainer=request.user
    ).values('student').distinct().count()

    # Fixed: Uses Enrollment and 'amount' field
    total_earnings = Enrollment.objects.filter(
        course__trainer=request.user
    ).aggregate(total=Sum('amount'))['total'] or 0

    course_stats = courses.annotate(
        students=Count('enrollment')
    )

    enrollments = Enrollment.objects.filter(course__trainer=request.user).select_related("student","course")

    student_progress = []

    for e in enrollments:
        total_lessons = Lesson.objects.filter(course=e.course).count()
        completed_lessons = LessonProgress.objects.filter(
            student=e.student,
            lesson__course=e.course,
            completed=True
        ).count()

        percent = int((completed_lessons / total_lessons) * 100) if total_lessons else 0

        student_progress.append({
            "name": e.student.username,
            "course": e.course.title,
            "completed": completed_lessons,
            "total": total_lessons,
            "percent": percent
        })

    return render(request, "trainer_analytics.html", {
        "total_courses": total_courses,
        "total_students": total_students,
        "total_earnings": total_earnings,
        "course_stats": course_stats,
        "student_progress": student_progress
    })

# ---------------- PROGRESS & PROFILE ----------------
@login_required
def complete_lesson(request, lesson_id):
    LessonProgress.objects.update_or_create(
        student=request.user,
        lesson_id=lesson_id,
        defaults={"completed":True}
    )
    return redirect(request.META.get("HTTP_REFERER"))

@login_required
def profile_view(request):
    user = request.user
    if request.method == 'POST':
        user.first_name = request.POST.get('full_name')
        user.contact_number = request.POST.get('contact')
        user.date_of_birth = request.POST.get('dob') or None
        user.current_state = request.POST.get('state')
        user.current_city = request.POST.get('city')
        user.college_name = request.POST.get('college')
        user.age = request.POST.get('age')
        user.gender = request.POST.get('gender')
        user.education = request.POST.get('education')
        user.save()
        return redirect('profile')
    return render(request, 'profile.html', {'user': user})

# ---------------- AUTHENTICATION ----------------
def login_view(request):
    if request.method == "POST":
        u = request.POST.get('username')
        p = request.POST.get('password')
        user = authenticate(request, username=u, password=p)
        if user:
            login(request, user)
            if user.is_trainer:
                return redirect('trainer_dashboard')
            return redirect('student_dashboard')
        
        messages.error(request, "Invalid username or password")
    
    return render(request, "login.html")

# ---------------- EDIT / DELETE ----------------
def edit_course(request, pk):
    course = get_object_or_404(Course, pk=pk)
    if request.method == "POST":
        course.title = request.POST.get('title')
        course.description = request.POST.get('description')
        course.price = request.POST.get('price')
        course.save()
        return redirect('trainer_courses')
    return render(request, 'edit_course.html', {'course': course})

def delete_course(request, pk):
    course = get_object_or_404(Course, pk=pk)
    course.delete()
    return redirect('trainer_courses')

def edit_lesson(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    if request.method == "POST":
        lesson.title = request.POST.get('title')
        lesson.order = request.POST.get('order')
        if request.FILES.get('video'):
            lesson.video = request.FILES.get('video')
        if request.FILES.get('notes'):
            lesson.notes = request.FILES.get('notes')
        lesson.save()
        return redirect('course_detail', course_id=lesson.course.id)
    return render(request, 'edit_lesson.html', {'lesson': lesson})

def delete_lesson(request, pk):
    lesson = get_object_or_404(Lesson, pk=pk)
    course_id = lesson.course.id
    if request.method == "POST":
        lesson.delete()
        return redirect('course_detail', course_id=course_id)
    return render(request, 'confirm_delete.html', {'lesson': lesson})


def course_learning_view(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    lessons = course.lessons.all().order_by('id') # Get all lessons for this course
    
    # Get the specific lesson from the URL (?lesson=5) or default to the first one
    lesson_id = request.GET.get('lesson')
    if lesson_id:
        current_lesson = get_object_or_404(Lesson, id=lesson_id)
    else:
        current_lesson = lessons.first()

    context = {
        'course': course,
        'lessons': lessons,
        'current_lesson': current_lesson,
    }
    return render(request, 'course_learning_page.html', context)

def send_support_query(request):
    if request.method == "POST":
        message = request.POST.get('message')
        # Create the query in the database
        SupportQuery.objects.create(
            student=request.user,
            message=message
        )
        messages.success(request, "Your doubt has been sent to the trainer!")
        return redirect('student_dashboard')
    
def resolve_query(request, query_id):
    if request.method == "POST":
        query = get_object_or_404(SupportQuery, id=query_id)
        answer_text = request.POST.get('answer')
        if answer_text:
            query.answer = answer_text
            query.is_resolved = True
            query.save()
            messages.success(request, f"Your reply has been sent to {query.student.username}!")
            return redirect('trainer_dashboard')
        else:
            messages.error(request, "Reply cannot be empty.")
            return redirect('trainer_dashboard')
        
    return redirect('trainer_dashboard')

def student_doubts(request):
    # Fetch all doubts asked by this specific student
    my_queries = SupportQuery.objects.filter(student=request.user).order_by('-created_at')
    
    return render(request, 'student_doubts.html', {'my_queries': my_queries})

@login_required
def join_live_class(request, id):
    live = get_object_or_404(LiveClass, id=id)

    if not Enrollment.objects.filter(student=request.user, course=live.course).exists():
        return HttpResponseForbidden("Not enrolled")

    return redirect(live.zoom_join_url)
