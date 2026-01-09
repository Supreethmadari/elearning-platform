from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .models import User, Profile  # Ensure Profile is imported

def register_view(request):
    if request.method == 'POST':
        # Capture all fields from our professional redesign
        username = request.POST.get('username')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        mobile = request.POST.get('mobile')
        password = request.POST.get('password')

        # 1. Validation Logic
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists")
            return redirect('register')

        if User.objects.filter(email=email).exists():
            messages.error(request, "Email already registered")
            return redirect('register')

        # 2. Create the User (using your custom User model fields)
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,  # Saves to standard Django field
            last_name=last_name,    # Saves to standard Django field
            is_student=True,
            is_trainer=False
        )
        user.save()

        # 3. Create the Profile for extra details (Mobile Number)
        # We use get_or_create to prevent errors if a profile exists
        Profile.objects.create(user=user, mobile=mobile)

        messages.success(request, f"Welcome {first_name}! Your account is ready.")
        login(request, user)
        return redirect('student_dashboard')

    return render(request, 'register.html')


def login_view(request):
    if request.method == "POST":
        # Using .get() is safer to avoid MultiValueDictKeyError
        username_val = request.POST.get('username')
        password_val = request.POST.get('password')
        
        user = authenticate(request, username=username_val, password=password_val)

        if user:
            login(request, user)
            # Professional Routing based on User Role
            if user.is_trainer:
                return redirect('trainer_dashboard')
            else:
                return redirect('student_dashboard')
        else:
            messages.error(request, "Invalid username or password")
            return redirect('login')

    return render(request, "login.html")


def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect("login")