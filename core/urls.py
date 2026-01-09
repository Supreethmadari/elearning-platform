"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from accounts import views as acc
from courses import views as course
from courses import views

from django.urls import path, include



urlpatterns = [
    path('admin/', admin.site.urls),
    path('', course.landing, name='landing'),
    path('landing/', views.home, name="home"),
    path('about/', views.about, name="about"),
    path('contact/', views.contact, name="contact"),
    path('explore/', views.explore, name="explore"),
    path('login/', acc.login_view, name='login'),
    path('register/', acc.register_view, name='register'),
    path('logout/', acc.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),

    # Student side
    path('student-dashboard/', course.student_dashboard, name='student_dashboard'),
    path('purchase/', course.purchase_course, name='purchase'),
    path('my-courses/', course.my_courses, name='my_courses'),
    path('learning/<int:course_id>/', views.course_learning_view, name='course_learning'),
    path('send-support-query/', views.send_support_query, name='send_support_query'),

    path('my-doubts/', views.student_doubts, name='student_doubts'),
    path("join-live/<int:id>/", views.join_live_class, name="join_live"),

    
    # Trainer side (Protected)
    path('trainer-dashboard/', course.trainer_dashboard, name='trainer_dashboard'),
    path('create-course/', course.create_course, name='create_course'),
    path('add-lesson/', course.add_lesson, name='add_lesson'),
    path("trainer-courses/", course.trainer_courses, name="trainer_courses"),
    path('course/<int:course_id>/', course.course_detail, name='course_detail'),
    path("checkout/<int:course_id>/", course.checkout, name="checkout"),
    path("payment-success/<int:course_id>/", course.payment_success, name="payment_success"),

    path("trainer-analytics/", course.trainer_analytics, name="trainer_analytics"),
    path('course/edit/<int:pk>/', views.edit_course, name='edit_course'),
    path('course/delete/<int:pk>/', views.delete_course, name='delete_course'),
    path('lesson/edit/<int:pk>/', views.edit_lesson, name='edit_lesson'),
    path('lesson/delete/<int:pk>/', views.delete_lesson, name='delete_lesson'),
    path('resolve-query/<int:query_id>/', views.resolve_query, name='resolve_query'),
    path("start-live/", views.start_live_class, name="start_live_class"),



    path('admin/', admin.site.urls),
    path('ai/', include('ai_chat.urls')),
]


from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)



