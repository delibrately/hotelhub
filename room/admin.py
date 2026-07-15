from django.contrib import admin

from main.services import log_room_created, log_room_updated

from .models import Room


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("room_number", "room_type", "price_per_night")
    ordering = ("room_number", "id")

    def save_model(self, request, obj, form, change):
        changed_fields = list(form.changed_data)
        super().save_model(request, obj, form, change)
        if change:
            if changed_fields:
                log_room_updated(operator=request.user, room=obj)
        else:
            log_room_created(operator=request.user, room=obj)
