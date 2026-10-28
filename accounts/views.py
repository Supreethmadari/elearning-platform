import random
from datetime import timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from .models import User, Profile, EmailOTP


def generate_and_send_otp(user):
    """Generate a 6-digit OTP, store in database, and dispatch via email."""
    # Invalidate previous unused OTPs for this user
    EmailOTP.objects.filter(user=user, is_used=False).update(is_used=True)

    code = f"{random.randint(100000, 999999)}"
    expires_at = timezone.now() + timedelta(minutes=15)

    EmailOTP.objects.create(
        user=user,
        code=code,
        expires_at=expires_at,
        is_used=False
    )

    subject = "Your Cyanopy Account Verification Code"
    message = (
        f"Hello {user.first_name or user.username},\n\n"
        f"Thank you for joining Cyanopy. Your 6-digit verification code is:\n\n"
        f"    {code}\n\n"
        f"This code will expire in 15 minutes.\n"
        f"If you did not request this code, please ignore this email.\n\n"
        f"Best regards,\nThe Cyanopy Team"
    )

    html_message = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #F8FAFC; margin: 0; padding: 0; color: #0F172A; }}
        .email-container {{ max-width: 540px; margin: 30px auto; background: #ffffff; border-radius: 16px; border: 1px solid #E2E8F0; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.05); }}
        .email-header {{ background: linear-gradient(135deg, #0B1120 0%, #0F172A 50%, #1E1B4B 100%); padding: 32px 24px; text-align: center; color: #ffffff; }}
        .brand-text {{ font-size: 26px; font-weight: 800; letter-spacing: 1.5px; color: #ffffff; }}
        .brand-o {{ color: #00D2C4; }}
        .brand-py {{ color: #7C3AED; }}
        .email-body {{ padding: 36px 32px; text-align: center; }}
        .greeting {{ font-size: 19px; font-weight: 800; color: #0F172A; margin-bottom: 12px; }}
        .lead-text {{ font-size: 14px; color: #64748B; line-height: 1.6; margin-bottom: 24px; }}
        .otp-box {{ background: #F8FAFC; border: 2px dashed #00D2C4; border-radius: 14px; padding: 16px 28px; font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #0F172A; margin: 16px auto 24px; display: inline-block; }}
        .expiry-note {{ font-size: 13px; color: #94A3B8; line-height: 1.5; }}
        .email-footer {{ background: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 20px; font-size: 12px; color: #94A3B8; text-align: center; }}
      </style>
    </head>
    <body>
      <div class="email-container">
        <div class="email-header">
          <div class="brand-text">CYAN<span class="brand-o">O</span><span class="brand-py">PY</span></div>
          <div style="font-size: 13px; color: #94A3B8; margin-top: 6px;">Email Verification Code</div>
        </div>
        <div class="email-body">
          <div class="greeting">Hello {user.first_name or user.username}!</div>
          <div class="lead-text">Thank you for joining Cyanopy. Enter the following 6-digit confirmation code on your verification screen to activate your account and proceed to course enrollment:</div>
          <div class="otp-box">{code}</div>
          <div class="expiry-note">⏳ This verification code will expire in <strong>15 minutes</strong>.<br>If you did not request this verification, please disregard this email.</div>
        </div>
        <div class="email-footer">
          &copy; 2026 Cyanopy Learning Technologies. All rights reserved.
        </div>
      </div>
    </body>
    </html>
    """

    try:
        send_mail(
            subject=subject,
            message=message,
            html_message=html_message,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'info@cyanopy.com'),
            recipient_list=[user.email],
            fail_silently=False
        )
    except Exception as e:
        print(f"[EMAIL SEND ERROR] {e}")

    # For development convenience, log code
    print(f"\n==========================================")
    print(f"[CYANOPY EMAIL OTP] To: {user.email} | CODE: {code}")
    print(f"==========================================\n")
    return code


@csrf_exempt
def register_view(request):
    if request.user.is_authenticated:
        if request.user.is_trainer:
            return redirect('trainer_dashboard')
        return redirect('student_dashboard')

    if request.method == 'POST':
        first_name = (request.POST.get('first_name') or '').strip()
        last_name = (request.POST.get('last_name') or '').strip()
        email = (request.POST.get('email') or '').strip().lower()
        mobile = (request.POST.get('mobile') or '').strip()
        password = request.POST.get('password') or ''
        confirm_password = request.POST.get('confirm_password') or ''

        # 1. Validation Logic
        if not email:
            messages.error(request, "Email address is required.")
            return render(request, 'register.html', request.POST)

        if not first_name:
            messages.error(request, "First name is required.")
            return render(request, 'register.html', request.POST)

        if password != confirm_password:
            messages.error(request, "Passwords do not match. Please try again.")
            return render(request, 'register.html', request.POST)

        if len(password) < 6:
            messages.error(request, "Password must be at least 6 characters long.")
            return render(request, 'register.html', request.POST)

        # Check existing user by email or username
        if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
            messages.error(request, "An account with this email already exists. Please sign in.")
            return redirect('login')

        # 2. Create the User (unverified until OTP is verified)
        user = User.objects.create_user(
            username=email,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            contact_number=mobile,
            is_student=True,
            is_trainer=False,
            is_verified=False
        )
        user.save()

        # Update or create Profile
        Profile.objects.update_or_create(user=user, defaults={'mobile': mobile})

        # 3. Generate and send 6-digit OTP
        generate_and_send_otp(user)

        # Store user ID in session for OTP verification
        request.session['pending_otp_user_id'] = user.id
        messages.success(request, f"Account created! We sent a 6-digit verification code to {email}.")
        return redirect('verify_otp')

    return render(request, 'register.html')


@csrf_exempt
def verify_otp_view(request):
    user_id = request.session.get('pending_otp_user_id')
    user = None

    if user_id:
        user = User.objects.filter(id=user_id).first()
    elif request.user.is_authenticated:
        user = request.user

    if not user:
        messages.warning(request, "Please register or enter your credentials to verify your account.")
        return redirect('register')

    if user.is_verified:
        messages.info(request, "Your account is already verified.")
        if request.user.is_authenticated:
            return redirect('course_enrollment')
        return redirect('login')

    if request.method == 'POST':
        otp_digit1 = request.POST.get('digit1', '')
        otp_digit2 = request.POST.get('digit2', '')
        otp_digit3 = request.POST.get('digit3', '')
        otp_digit4 = request.POST.get('digit4', '')
        otp_digit5 = request.POST.get('digit5', '')
        otp_digit6 = request.POST.get('digit6', '')
        
        entered_code = f"{otp_digit1}{otp_digit2}{otp_digit3}{otp_digit4}{otp_digit5}{otp_digit6}".strip()
        
        # Fallback for single input field
        if not entered_code or len(entered_code) < 6:
            entered_code = (request.POST.get('otp_code') or '').strip()

        # Find latest active OTP
        otp_record = EmailOTP.objects.filter(
            user=user,
            code=entered_code,
            is_used=False,
            expires_at__gte=timezone.now()
        ).order_by('-created_at').first()

        if otp_record:
            # Mark OTP as used
            otp_record.is_used = True
            otp_record.save()

            # Mark user verified
            user.is_verified = True
            user.save()

            # Clean session
            if 'pending_otp_user_id' in request.session:
                del request.session['pending_otp_user_id']

            # Authenticate user session for enrollment
            login(request, user)
            messages.success(request, "Email verified successfully! Please select your course to complete enrollment.")
            return redirect('course_enrollment')
        else:
            messages.error(request, "Invalid or expired verification code. Please check and try again.")

    return render(request, 'verify_otp.html', {'target_email': user.email})


@csrf_exempt
def resend_otp_view(request):
    user_id = request.session.get('pending_otp_user_id')
    user = None
    if user_id:
        user = User.objects.filter(id=user_id).first()
    elif request.user.is_authenticated:
        user = request.user

    if not user:
        messages.error(request, "Session expired. Please sign up or log in again.")
        return redirect('register')

    generate_and_send_otp(user)
    messages.success(request, f"A fresh 6-digit code has been dispatched to {user.email}.")
    return redirect('verify_otp')


@csrf_exempt
def login_view(request):
    if request.method == "GET" and request.user.is_authenticated:
        if request.user.is_trainer or request.user.is_staff or request.user.is_superuser:
            return redirect('trainer_dashboard')
        return redirect('student_dashboard')

    if request.method == "POST":
        identifier = (request.POST.get("email") or request.POST.get("username") or '').strip()
        password = request.POST.get("password") or ''

        # Match user by email first, fallback to username
        matched_user = User.objects.filter(email__iexact=identifier).first()
        if not matched_user:
            matched_user = User.objects.filter(username__iexact=identifier).first()

        auth_username = matched_user.username if matched_user else identifier
        user = authenticate(request, username=auth_username, password=password)

        if user is not None:
            # 1. Verification check for students
            if user.is_student and not user.is_verified:
                request.session['pending_otp_user_id'] = user.id
                generate_and_send_otp(user)
                messages.warning(request, "Your email is not verified yet. We sent a 6-digit code to complete verification.")
                return redirect('verify_otp')

            # 2. Login authenticated user
            login(request, user)

            # Route based on role
            if user.is_trainer or user.is_staff or user.is_superuser:
                return redirect("trainer_dashboard")

            # Student enrollment check
            from courses.models import Enrollment
            active_enrollment = Enrollment.objects.filter(student=user, status__in=['ACTIVE', 'COMPLETED']).first()
            if active_enrollment:
                return redirect("student_dashboard")

            # Check if student has pending verification enrollment
            pending_enrollment = Enrollment.objects.filter(student=user, status='PENDING_VERIFICATION').first()
            if pending_enrollment:
                messages.info(request, "Your course payment is currently under manual verification.")
                return redirect("enrollment_status")

            rejected_enrollment = Enrollment.objects.filter(student=user, status='REJECTED').first()
            if rejected_enrollment:
                messages.error(request, "Your previous manual payment could not be verified.")
                return redirect("enrollment_status")

            partial_enrollment = Enrollment.objects.filter(student=user, status='PENDING_PAYMENT').first()
            if partial_enrollment:
                return redirect("enrollment_status")

            # No enrollments yet -> redirect to course selection
            return redirect("course_enrollment")

        messages.error(request, "Invalid email address or password. Please try again.")

    return render(request, "login.html")


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("login")