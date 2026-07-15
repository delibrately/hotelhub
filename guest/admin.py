from django.contrib import admin

from main.services import log_guest_created, log_guest_updated

from .models import Guest


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ("id", "first_name", "last_name", "email")
    ordering = ("-id",)

    def save_model(self, request, obj, form, change):
        changed_fields = list(form.changed_data)
        super().save_model(request, obj, form, change)
        if change:
            if changed_fields:
                log_guest_updated(operator=request.user, guest=obj)
        else:
            log_guest_created(operator=request.user, guest=obj)
