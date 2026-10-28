from django.contrib import admin
from .models import AIChatMessage


@admin.register(AIChatMessage)
class AIChatMessageAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'course', 'lesson', 'created_at', 'short_content')
    list_filter = ('role', 'course', 'created_at')
    search_fields = ('user__username', 'content')

    def short_content(self, obj):
        return obj.content[:60] + "..." if len(obj.content) > 60 else obj.content
