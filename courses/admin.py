from django.contrib import admin
from django.utils import timezone
from .models import Course, Lesson, StudentCertificate, Enrollment, Payment


class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'course', 'tier', 'amount', 'status', 'completed', 'created_at')
    list_filter = ('status', 'completed', 'tier', 'course')
    search_fields = ('student__username', 'student__email', 'course__title')
    list_editable = ('status',)


class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'student', 'course', 'tier', 'course_fee', 'claimed_amount',
        'verified_amount', 'remaining_amount', 'payment_method', 'status',
        'payment_date', 'payment_reference', 'verified_by'
    )
    list_filter = ('status', 'payment_method', 'payment_date', 'course')
    search_fields = ('student__username', 'student__email', 'payment_reference', 'course__title')
    readonly_fields = ('created_at', 'updated_at')

    actions = ['confirm_full_payment', 'reject_payment']

    def confirm_full_payment(self, request, queryset):
        for payment in queryset:
            payment.verified_amount = payment.course_fee
            payment.remaining_amount = 0
            payment.status = 'PAID'
            payment.verified_by = request.user
            payment.verified_at = timezone.now()
            payment.save()
            if payment.enrollment:
                payment.enrollment.status = 'ACTIVE'
                payment.enrollment.save()
        self.message_user(request, f"Successfully confirmed full payment for {queryset.count()} record(s).")
    confirm_full_payment.short_description = "Confirm Full Payment (Activate Enrollment)"

    def reject_payment(self, request, queryset):
        for payment in queryset:
            payment.status = 'REJECTED'
            payment.admin_notes = "Payment could not be verified by administrator."
            payment.verified_by = request.user
            payment.verified_at = timezone.now()
            payment.save()
            if payment.enrollment:
                payment.enrollment.status = 'REJECTED'
                payment.enrollment.save()
        self.message_user(request, f"Successfully rejected {queryset.count()} payment(s).")
    reject_payment.short_description = "Reject Selected Payments"


admin.site.register(Course)
admin.site.register(Lesson)
admin.site.register(StudentCertificate)
admin.site.register(Enrollment, EnrollmentAdmin)
admin.site.register(Payment, PaymentAdmin)
