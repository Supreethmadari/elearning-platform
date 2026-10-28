from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Profile, EmailOTP

class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_verified', 'is_student', 'is_trainer', 'is_staff')
    list_filter = ('is_verified', 'is_student', 'is_trainer', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name')

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'contact_number', 'college_name', 'education')}),
        ('Verification & Role', {'fields': ('is_verified', 'is_student', 'is_trainer')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
    )

class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ('user', 'code', 'expires_at', 'is_used', 'created_at')
    list_filter = ('is_used', 'created_at')
    search_fields = ('user__email', 'user__username', 'code')

admin.site.register(User, UserAdmin)
admin.site.register(Profile)
admin.site.register(EmailOTP, EmailOTPAdmin)
