from django.db import models
from django.utils import timezone


class Room(models.Model):
    room_number = models.CharField(max_length=10, unique=True)
    room_type = models.CharField(max_length=50)
    price_per_night = models.DecimalField(max_digits=8, decimal_places=2)

    def is_booked_now(self):
        from main.models import Reservation

        today = timezone.localdate()
        return self.reservation_set.filter(
            status__in=Reservation.OCCUPYING_STATUSES,
            check_in_date__lte=today,
            check_out_date__gt=today,
        ).exists()

    def __str__(self):
        return self.room_number
