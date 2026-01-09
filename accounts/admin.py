from django.contrib import admin
from .models import User

class UserAdmin(admin.ModelAdmin):
    list_display = ('username', 'email', 'is_student', 'is_trainer', 'is_staff')
    list_filter = ('is_student', 'is_trainer')
    search_fields = ('username', 'email')

    fieldsets = (
        ('Basic Info', {'fields': ('username', 'password', 'email')}),
        ('Permissions', {'fields': ('is_student', 'is_trainer', 'is_staff', 'is_superuser')}),
        ('Personal Info', {'fields': ('contact_number','college_name','education')}),
    )

admin.site.register(User, UserAdmin)
