from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.http import HttpResponseForbidden
from django.db.models import Count, Sum
from decimal import Decimal
from .models import Course, Lesson, Enrollment, LessonProgress, StudentProgress, LiveClass, StudentCertificate, Payment
from .models import SupportQuery
from django.utils import timezone
from .zoom_service import create_meeting
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .certificate_engine import generate_certificate
import razorpay
from django.conf import settings


# ---------------- SECURE TRAINER DECORATOR ----------------
def trainer_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        if not (request.user.is_trainer or request.user.is_staff or request.user.is_superuser):
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
    courses = Course.objects.all()
    return render(request, "explore.html", {"courses": courses})


#---------------- PAID REGISTRATION FLOW ----------------
def register_view(request):
    course_id = request.GET.get("course")

    if request.method == "POST":
        request.session["pending_user"] = {
            "username": request.POST["username"],
            "password": request.POST["password"],
            "email": request.POST["email"],
            "course_id": course_id
        }
        return redirect("checkout", course_id)

    return render(request, "register.html", {"course_id": course_id})





# ---------------- STUDENT DASHBOARD ----------------
@login_required(login_url='login')
def student_dashboard(request):
    if request.user.is_trainer or request.user.is_staff:
        return redirect('trainer_dashboard')

    if not getattr(request.user, 'is_verified', True):
        messages.warning(request, "Please verify your email address to access your dashboard.")
        request.session['pending_otp_user_id'] = request.user.id
        return redirect('verify_otp')

    purchases = Enrollment.objects.filter(student=request.user, status__in=['ACTIVE', 'COMPLETED'])
    enrolled_courses_count = purchases.count()

    if enrolled_courses_count == 0:
        if Enrollment.objects.filter(student=request.user, status='PENDING_VERIFICATION').exists():
            return redirect('enrollment_status')
        elif Enrollment.objects.filter(student=request.user, status='REJECTED').exists():
            return redirect('enrollment_status')
        elif Enrollment.objects.filter(student=request.user, status='PENDING_PAYMENT').exists():
            return redirect('enrollment_status')
        return redirect('course_enrollment')

    progress = StudentProgress.objects.filter(student=request.user)
    total_hours = progress.aggregate(total=Sum("hours_spent"))["total"] or 0

    certificates = progress.filter(is_completed=True).count()
    certificates_list = StudentCertificate.objects.filter(student=request.user)

    now = timezone.now()

    active_live = LiveClass.objects.filter(
        is_active=True,
        start_time__lte=now,
        end_time__gte=now
    )

    live_map = {l.course_id: l for l in active_live}

    current_learning_courses = []
    enrolled_courses = []
    for p in purchases:
        course = p.course
        all_lessons = list(course.lessons.all().order_by('order', 'id'))
        total_lessons = len(all_lessons)

        completed_ids = set(
            LessonProgress.objects.filter(
                student=request.user,
                lesson__course=course,
                completed=True
            ).values_list('lesson_id', flat=True)
        )
        completed_count = len(completed_ids)
        progress_pct = int((completed_count / total_lessons) * 100) if total_lessons > 0 else 0

        # Next / Current lesson where student left off:
        next_lesson = None
        for l in all_lessons:
            if l.id not in completed_ids:
                next_lesson = l
                break

        if not next_lesson and all_lessons:
            next_lesson = all_lessons[-1]

        course_item = {
            "enrollment": p,
            "course": course,
            "tier": p.tier or "Online Course",
            "total_lessons": total_lessons,
            "completed_count": completed_count,
            "progress_pct": progress_pct,
            "next_lesson": next_lesson,
            "is_completed": (completed_count == total_lessons and total_lessons > 0),
            "live": live_map.get(course.id)
        }
        current_learning_courses.append(course_item)
        enrolled_courses.append(course_item)

    return render(request, "student_dashboard.html", {
        "current_learning_courses": current_learning_courses,
        "enrolled_courses": enrolled_courses,
        "enrolled_courses_count": enrolled_courses_count,
        "learning_hours": round(total_hours, 1),
        "certificates": certificates,
        "certificates_list": certificates_list,
        "progress": progress
    })


@login_required(login_url='login')
def purchase_course(request):
    courses = Course.objects.all().order_by('-id')
    enrolled_ids = []
    if request.user.is_authenticated:
        enrolled_ids = list(Enrollment.objects.filter(
            student=request.user,
            status__in=['ACTIVE', 'COMPLETED']
        ).values_list('course_id', flat=True))
    return render(request, "purchase.html", {"courses": courses, "enrolled_ids": enrolled_ids})

@login_required
def my_courses(request):
    purchases = Enrollment.objects.filter(student=request.user, status__in=['ACTIVE', 'COMPLETED'])
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


@login_required
def create_course(request):
    if request.method == "POST":

        def to_int(value):
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0

        new_course = Course.objects.create(
            trainer=request.user,
            title=request.POST.get('title'),
            description=request.POST.get('description'),
            price=to_int(request.POST.get('price')),

            live_virtual_old_price=to_int(request.POST.get('live_old')),
            live_virtual_new_price=to_int(request.POST.get('live_new')),

            blended_old_price=to_int(request.POST.get('blended_old')),
            blended_new_price=to_int(request.POST.get('blended_new')),

            classroom_old_price=to_int(request.POST.get('class_old')),
            classroom_new_price=to_int(request.POST.get('class_new')),
        )

        messages.success(request, "Course created successfully!")
        return redirect('trainer_dashboard')

    return render(request, 'create_course.html')



@trainer_required
def trainer_courses(request):
    courses = Course.objects.filter(trainer=request.user)
    return render(request, "trainer_courses.html", {"courses": courses})


@trainer_required
def start_live_class(request):
    if request.method == "POST":
        title = request.POST.get("title", "Live Class")
        course_id = request.POST.get("course")
        try:
            duration = int(request.POST.get("duration", 60) or 60)
        except (ValueError, TypeError):
            duration = 60
        meeting_link = request.POST.get("meeting_link", "").strip()

        zoom = create_meeting(title, duration, meeting_link=meeting_link, course_id=course_id)

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

        return redirect(live.zoom_start_url)

    return redirect("trainer_dashboard")




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
def get_tier_price(course, tier):
    tier = (tier or 'Live Virtual').strip()
    if tier == 'Blended' and course.blended_new_price > 0:
        return course.blended_new_price
    elif tier == 'Classroom' and course.classroom_new_price > 0:
        return course.classroom_new_price
    elif course.live_virtual_new_price > 0:
        return course.live_virtual_new_price
    return course.price


@csrf_exempt
@login_required
def course_enrollment(request):
    if not getattr(request.user, 'is_verified', True):
        messages.warning(request, "Please verify your email address before enrolling.")
        request.session['pending_otp_user_id'] = request.user.id
        return redirect('verify_otp')

    # Auto-seed default courses on fresh production database
    if not Course.objects.exists():
        Course.objects.create(
            title="Full Stack Python & AI Masterclass",
            description="Comprehensive career program covering Python, Django, REST APIs, PostgreSQL, and LLM AI development.",
            price=15000,
            live_virtual_old_price=20000,
            live_virtual_new_price=14999,
            blended_old_price=16000,
            blended_new_price=11999,
            classroom_old_price=25000,
            classroom_new_price=19999,
            trainer=request.user,
            rating=4.9
        )
        Course.objects.create(
            title="Data Science & Machine Learning Bootcamp",
            description="Master Pandas, NumPy, Deep Learning, Computer Vision, and real-time model deployment.",
            price=18000,
            live_virtual_old_price=24000,
            live_virtual_new_price=17999,
            blended_old_price=18000,
            blended_new_price=13999,
            classroom_old_price=30000,
            classroom_new_price=24999,
            trainer=request.user,
            rating=5.0
        )

    courses = Course.objects.all()
    selected_course_id = request.GET.get('course_id') or request.POST.get('course_id')
    selected_course = None
    if selected_course_id:
        selected_course = Course.objects.filter(id=selected_course_id).first()
    if not selected_course and courses.exists():
        selected_course = courses.first()

    if request.method == 'POST':
        action = request.POST.get('action')
        course_id = request.POST.get('course_id')
        tier = request.POST.get('tier') or 'Live Virtual'
        course = get_object_or_404(Course, id=course_id)
        course_fee = Decimal(str(get_tier_price(course, tier)))

        if action == 'pay_online':
            return redirect(f"/checkout/{course.id}/?tier={tier}")

        elif action == 'manual_payment':
            amount_paid_str = (request.POST.get('amount_paid') or '').strip()
            payment_date_str = (request.POST.get('payment_date') or '').strip()
            payment_method = request.POST.get('payment_method') or 'UPI'
            payment_reference = (request.POST.get('payment_reference') or '').strip()
            student_notes = (request.POST.get('student_notes') or '').strip()

            if not amount_paid_str:
                messages.error(request, "Amount Paid is required for manual payment verification.")
                return render(request, "course_enrollment.html", {
                    "courses": courses,
                    "selected_course": course,
                    "selected_tier": tier,
                })

            try:
                amount_paid = Decimal(amount_paid_str)
                if amount_paid <= 0:
                    raise ValueError
            except (ValueError, TypeError):
                messages.error(request, "Please enter a valid positive number for Amount Paid.")
                return render(request, "course_enrollment.html", {
                    "courses": courses,
                    "selected_course": course,
                    "selected_tier": tier,
                })

            # Check if active enrollment already exists
            existing_active = Enrollment.objects.filter(student=request.user, course=course, status__in=['ACTIVE', 'COMPLETED']).first()
            if existing_active:
                messages.info(request, f"You are already actively enrolled in {course.title}.")
                return redirect('student_dashboard')

            # Create or update Enrollment
            enrollment, _ = Enrollment.objects.update_or_create(
                student=request.user,
                course=course,
                defaults={
                    "tier": tier,
                    "status": "PENDING_VERIFICATION",
                    "amount": course_fee,
                    "completed": False,
                }
            )

            # Create or update Payment claim
            Payment.objects.update_or_create(
                enrollment=enrollment,
                defaults={
                    "student": request.user,
                    "course": course,
                    "tier": tier,
                    "course_fee": course_fee,
                    "claimed_amount": amount_paid,
                    "verified_amount": Decimal('0.00'),
                    "remaining_amount": course_fee,
                    "payment_method": payment_method,
                    "payment_date": payment_date_str or timezone.now().date(),
                    "payment_reference": payment_reference,
                    "student_notes": student_notes,
                    "status": "PENDING_VERIFICATION",
                    "verified_by": None,
                    "verified_at": None,
                }
            )

            messages.success(request, "Your manual payment details have been submitted for verification.")
            return redirect('enrollment_status')

    return render(request, "course_enrollment.html", {
        "courses": courses,
        "selected_course": selected_course,
    })


@login_required
def enrollment_status(request):
    enrollments = Enrollment.objects.filter(student=request.user).select_related('course').order_by('-updated_at')
    latest_enrollment = enrollments.first()
    payment = None
    if latest_enrollment:
        payment = getattr(latest_enrollment, 'payment', None)
        if not payment:
            payment = Payment.objects.filter(enrollment=latest_enrollment).first()

    show_welcome = request.GET.get('welcome') == '1' or (latest_enrollment and latest_enrollment.status == 'ACTIVE' and request.session.pop('just_enrolled', False))

    return render(request, "enrollment_status.html", {
        "enrollment": latest_enrollment,
        "payment": payment,
        "show_welcome": show_welcome,
    })


@login_required
def checkout(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    tier = request.GET.get('tier', 'Live Virtual')
    is_balance = request.GET.get('balance') == '1'

    standard_fee = get_tier_price(course, tier)
    fee = standard_fee

    existing_payment = Payment.objects.filter(student=request.user, course=course).first()
    if is_balance and existing_payment and existing_payment.remaining_amount > 0:
        fee = existing_payment.remaining_amount

    # Razorpay Order Initialization
    razorpay_order_id = ""
    order_amount_paise = int(Decimal(str(fee)) * 100)
    razorpay_key_id = getattr(settings, 'RAZORPAY_KEY_ID', '')
    razorpay_key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')

    if razorpay_key_id and razorpay_key_secret:
        try:
            client = razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))
            # Receipt identifier (max 40 chars)
            receipt_code = f"c_{course.id}_u_{request.user.id}_{int(timezone.now().timestamp())}"[:38]
            order_data = {
                "amount": order_amount_paise,
                "currency": "INR",
                "receipt": receipt_code,
                "notes": {
                    "course_id": str(course.id),
                    "course_title": course.title[:45],
                    "student_username": request.user.username,
                    "tier": tier,
                }
            }
            order = client.order.create(data=order_data)
            razorpay_order_id = order.get('id', '')
        except Exception as e:
            print(f"[RAZORPAY ORDER ERROR] {e}")

    return render(request, "payment_gateway.html", {
        "course": course,
        "tier": tier,
        "fee": fee,
        "is_balance": is_balance,
        "existing_payment": existing_payment,
        "razorpay_key_id": razorpay_key_id,
        "razorpay_order_id": razorpay_order_id,
        "order_amount_paise": order_amount_paise,
    })


@csrf_exempt
@login_required
def payment_success(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    tier = request.POST.get('tier') or request.GET.get('tier') or 'Live Virtual'
    is_balance = request.POST.get('is_balance') == '1'

    razorpay_payment_id = request.POST.get('razorpay_payment_id')
    razorpay_order_id = request.POST.get('razorpay_order_id')
    razorpay_signature = request.POST.get('razorpay_signature')

    fee = Decimal(str(get_tier_price(course, tier)))

    # 1. Cryptographic Razorpay Signature Verification
    if razorpay_payment_id and razorpay_order_id and razorpay_signature:
        razorpay_key_id = getattr(settings, 'RAZORPAY_KEY_ID', '')
        razorpay_key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', '')
        client = razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))

        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })
            payment_ref = razorpay_payment_id
        except razorpay.errors.SignatureVerificationError:
            messages.error(request, "Payment signature verification failed. Untrusted payment blocked.")
            return redirect(f"/checkout/{course.id}/?tier={tier}")
        except Exception as err:
            messages.error(request, f"Payment verification error: {err}")
            return redirect(f"/checkout/{course.id}/?tier={tier}")
    else:
        # Fallback card validation
        card_name = (request.POST.get('cardholder_name') or '').strip()
        card_number = (request.POST.get('card_number') or '').replace(' ', '').strip()
        if not card_name or len(card_number) < 12:
            messages.error(request, "Payment could not be verified. Please try again.")
            return redirect(f"/checkout/{course.id}/?tier={tier}")
        payment_ref = f"CYN-ONL-{timezone.now().strftime('%Y%m%d%H%M%S')}"

    # 2. Update Balance or Activate New Course Enrollment
    if is_balance:
        payment = Payment.objects.filter(student=request.user, course=course).first()
        if payment:
            payment.verified_amount = payment.course_fee
            payment.remaining_amount = Decimal('0.00')
            payment.status = 'PAID'
            payment.payment_method = 'ONLINE'
            payment.payment_reference = payment_ref
            payment.save()

            if payment.enrollment:
                payment.enrollment.status = 'ACTIVE'
                payment.enrollment.save()
            else:
                Enrollment.objects.update_or_create(
                    student=request.user,
                    course=course,
                    defaults={"tier": tier, "status": "ACTIVE", "amount": payment.course_fee}
                )
    else:
        enrollment, _ = Enrollment.objects.update_or_create(
            student=request.user,
            course=course,
            defaults={
                "tier": tier,
                "status": "ACTIVE",
                "amount": fee,
                "completed": False,
            }
        )

        Payment.objects.update_or_create(
            enrollment=enrollment,
            defaults={
                "student": request.user,
                "course": course,
                "tier": tier,
                "course_fee": fee,
                "claimed_amount": fee,
                "verified_amount": fee,
                "remaining_amount": Decimal('0.00'),
                "payment_method": "ONLINE",
                "payment_date": timezone.now().date(),
                "payment_reference": payment_ref,
                "status": "PAID",
                "verified_by": None,
                "verified_at": timezone.now(),
            }
        )

    # Set flag to display Welcome Dialog on Dashboard
    request.session['just_enrolled'] = True
    return redirect('/enrollment-status/?welcome=1')


@csrf_exempt
@trainer_required
def trainer_verify_payments(request):
    filter_status = request.GET.get('status', 'PENDING_VERIFICATION')
    
    payments = Payment.objects.select_related('student', 'course', 'enrollment', 'verified_by').order_by('-created_at')
    if filter_status != 'ALL':
        payments = payments.filter(status=filter_status)

    if request.method == 'POST':
        payment_id = request.POST.get('payment_id')
        action = request.POST.get('action')
        payment_item = get_object_or_404(Payment, id=payment_id)

        if action == 'confirm':
            verified_amount_str = (request.POST.get('verified_amount') or '').strip()
            admin_notes = (request.POST.get('admin_notes') or '').strip()

            try:
                verified_amount = Decimal(verified_amount_str)
                if verified_amount < 0:
                    raise ValueError
            except (ValueError, TypeError):
                messages.error(request, "Please enter a valid positive number for verified amount.")
                return redirect('trainer_verify_payments')

            payment_item.verified_amount = verified_amount
            payment_item.admin_notes = admin_notes
            payment_item.verified_by = request.user
            payment_item.verified_at = timezone.now()

            if verified_amount >= payment_item.course_fee:
                payment_item.remaining_amount = Decimal('0.00')
                payment_item.status = 'PAID'
                if payment_item.enrollment:
                    payment_item.enrollment.status = 'ACTIVE'
                    payment_item.enrollment.save()
                messages.success(request, f"Full payment of ₹{verified_amount} verified! Enrollment for {payment_item.student.username} is now ACTIVE.")
            else:
                remaining = payment_item.course_fee - verified_amount
                payment_item.remaining_amount = remaining
                payment_item.status = 'PARTIALLY_PAID'
                if payment_item.enrollment:
                    payment_item.enrollment.status = 'PENDING_PAYMENT'
                    payment_item.enrollment.save()
                messages.warning(request, f"Partial payment of ₹{verified_amount} confirmed. Remaining balance: ₹{remaining}. Status set to PARTIALLY_PAID.")

            payment_item.save()
            return redirect(f"/trainer/verify-payments/?status={filter_status}")

        elif action == 'reject':
            rejection_reason = (request.POST.get('rejection_reason') or 'Payment details could not be verified.').strip()

            payment_item.status = 'REJECTED'
            payment_item.admin_notes = rejection_reason
            payment_item.verified_by = request.user
            payment_item.verified_at = timezone.now()
            payment_item.save()

            if payment_item.enrollment:
                payment_item.enrollment.status = 'REJECTED'
                payment_item.enrollment.save()

            messages.error(request, f"Payment claim for {payment_item.student.username} rejected.")
            return redirect(f"/trainer/verify-payments/?status={filter_status}")

    counts = {
        'pending': Payment.objects.filter(status='PENDING_VERIFICATION').count(),
        'partial': Payment.objects.filter(status='PARTIALLY_PAID').count(),
        'paid': Payment.objects.filter(status='PAID').count(),
        'rejected': Payment.objects.filter(status='REJECTED').count(),
        'total': Payment.objects.count()
    }

    return render(request, "trainer_verify_payments.html", {
        "payments": payments,
        "filter_status": filter_status,
        "counts": counts
    })

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
        students=Count('enrollments')
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
    lesson = get_object_or_404(Lesson, id=lesson_id)

    obj, created = LessonProgress.objects.get_or_create(
        student=request.user,
        lesson=lesson
    )
    obj.completed = True
    obj.save()

    total = Lesson.objects.filter(course=lesson.course).count()
    done = LessonProgress.objects.filter(
        student=request.user,
        lesson__course=lesson.course,
        completed=True
    ).count()

    progress, _ = StudentProgress.objects.get_or_create(
        student=request.user,
        course=lesson.course,
        defaults={"total_lessons": total}
    )

    progress.completed_lessons = done
    progress.total_lessons = total
    progress.update_status()

    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
        return JsonResponse({
            'status': 'ok',
            'completed': obj.completed,
            'completed_count': done,
            'total_lessons': total,
            'progress_pct': int((done / total) * 100) if total else 0
        })

    referer = request.META.get("HTTP_REFERER")
    if referer:
        return redirect(referer)
    return redirect('course_learning', course_id=lesson.course.id)

@login_required
def profile_view(request):
    user = request.user
    if request.method == 'POST':
        full_name = (request.POST.get('full_name') or '').strip()
        if full_name:
            name_parts = full_name.split(' ', 1)
            user.first_name = name_parts[0]
            user.last_name = name_parts[1] if len(name_parts) > 1 else ''
        else:
            user.first_name = ''
            user.last_name = ''
            
        user.contact_number = request.POST.get('contact') or ''
        user.date_of_birth = request.POST.get('dob') or None
        user.current_state = request.POST.get('state') or ''
        user.current_city = request.POST.get('city') or ''
        user.college_name = request.POST.get('college') or ''
        age_val = request.POST.get('age')
        user.age = int(age_val) if age_val and age_val.isdigit() else None
        user.gender = request.POST.get('gender') or ''
        user.education = request.POST.get('education') or ''
        user.save()
        messages.success(request, "Account settings updated successfully!")
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
        # Basic Info
        course.title = request.POST.get('title')
        course.description = request.POST.get('description')
        course.price = request.POST.get('price') or 0
        
        # Live Virtual
        course.live_virtual_old_price = request.POST.get('live_old') or 0
        course.live_virtual_new_price = request.POST.get('live_new') or 0
        
        # Blended
        course.blended_old_price = request.POST.get('blended_old') or 0
        course.blended_new_price = request.POST.get('blended_new') or 0
        
        # Classroom
        course.classroom_old_price = request.POST.get('class_old') or 0
        course.classroom_new_price = request.POST.get('class_new') or 0
        
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
    lessons = list(course.lessons.all().order_by('order', 'id'))
    lesson_id = request.GET.get('lesson')
    
    current_lesson = None
    if lesson_id:
        try:
            current_lesson = course.lessons.get(id=int(lesson_id))
        except (Lesson.DoesNotExist, ValueError):
            current_lesson = lessons[0] if lessons else None
    elif lessons:
        current_lesson = lessons[0]

    prev_lesson = None
    next_lesson = None
    if current_lesson and current_lesson in lessons:
        curr_idx = lessons.index(current_lesson)
        if curr_idx > 0:
            prev_lesson = lessons[curr_idx - 1]
        if curr_idx < len(lessons) - 1:
            next_lesson = lessons[curr_idx + 1]

    completed_lesson_ids = set()
    is_current_completed = False
    progress_pct = 0
    if request.user.is_authenticated and current_lesson:
        completed_lesson_ids = set(
            LessonProgress.objects.filter(
                student=request.user,
                lesson__course=course,
                completed=True
            ).values_list('lesson_id', flat=True)
        )
        is_current_completed = current_lesson.id in completed_lesson_ids
        if lessons:
            progress_pct = int((len(completed_lesson_ids) / len(lessons)) * 100)

    context = {
        'course': course,
        'lessons': lessons,
        'current_lesson': current_lesson,
        'prev_lesson': prev_lesson,
        'next_lesson': next_lesson,
        'completed_lesson_ids': completed_lesson_ids,
        'is_current_completed': is_current_completed,
        'progress_pct': progress_pct,
    }
    return render(request, 'course_learning_page.html', context)

@login_required
def send_support_query(request):
    if request.method == "POST":
        message = request.POST.get('message')
        if message and message.strip():
            SupportQuery.objects.create(
                student=request.user,
                message=message.strip()
            )
            messages.success(request, "Your doubt has been sent to the trainer!")
        return redirect(request.META.get('HTTP_REFERER', 'student_dashboard'))
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

@login_required
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


@login_required
def update_lesson_progress(request):
    lesson_id = request.POST.get("lesson_id")
    watched = int(request.POST.get("watched", 0))
    completed = request.POST.get("completed") == "true"

    obj, _ = LessonProgress.objects.get_or_create(
        student=request.user,
        lesson_id=lesson_id
    )

    obj.watched_seconds = max(obj.watched_seconds, watched)

    if completed:
        obj.completed = True

    obj.save()
    return JsonResponse({"status": "ok"})


def course_public_detail(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    lessons = course.lessons.all().order_by('order') 
    
    return render(request, 'course_public_detail.html', {
        'course': course,
        'lessons': lessons
    })


@login_required
def trainer_course_view(request, pk):
    # Ensure only the trainer who owns the course can see this specific management view
    course = get_object_or_404(Course, pk=pk, trainer=request.user)
    lessons = course.lessons.all().order_by('order')
    
    return render(request, 'trainer_course_view.html', {
        'course': course,
        'lessons': lessons
    })