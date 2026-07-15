from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse


class Reservation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "待确认"
        CONFIRMED = "confirmed", "已确认"
        CHECKED_IN = "checked_in", "已入住"
        CHECKED_OUT = "checked_out", "已退房"
        CANCELLED = "cancelled", "已取消"
        NO_SHOW = "no_show", "未到店"

    OCCUPYING_STATUSES = (
        Status.PENDING,
        Status.CONFIRMED,
        Status.CHECKED_IN,
    )

    room = models.ForeignKey("room.Room", on_delete=models.PROTECT)
    guest = models.ForeignKey("guest.Guest", on_delete=models.PROTECT)
    additional = models.TextField(null=True, blank=True)
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(check_in_date__lt=models.F("check_out_date")),
                name="reservation_check_in_before_check_out",
            ),
        ]
        permissions = [
            (
                "manage_reservation_status",
                "Can confirm, cancel, check in, check out, and mark no-show",
            ),
        ]

    def clean(self):
        super().clean()

        if not self.check_in_date or not self.check_out_date:
            return

        if self.check_in_date >= self.check_out_date:
            raise ValidationError(
                {"check_out_date": "Check-out date must be after check-in date."}
            )

        if not self.room_id:
            return

        if self.status not in self.OCCUPYING_STATUSES:
            return

        conflicts = Reservation.objects.filter(
            room_id=self.room_id,
            status__in=self.OCCUPYING_STATUSES,
            check_in_date__lt=self.check_out_date,
            check_out_date__gt=self.check_in_date,
        )
        if self.pk:
            conflicts = conflicts.exclude(pk=self.pk)

        if conflicts.exists():
            raise ValidationError(
                {"room": "This room is already booked for the selected dates."}
            )

    def get_absolute_url(self):
        return reverse("reservation_detail", args=[str(self.id)])

    def __str__(self):
        return (
            f"{self.room.room_number} | "
            f"from {self.check_in_date} to {self.check_out_date}"
        )


class ReservationNote(models.Model):
    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name="notes",
    )
    content = models.TextField(max_length=5000)
    is_important = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reservation_notes",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["reservation", "created_at"],
                name="main_note_res_created_idx",
            ),
        ]

    def __str__(self):
        return f"Reservation note #{self.pk} for reservation #{self.reservation_id}"


class AdminOperationLog(models.Model):
    class Action(models.TextChoices):
        RESERVATION_CREATED = "reservation_created", "创建订单"
        RESERVATION_UPDATED = "reservation_updated", "修改订单"
        RESERVATION_CONFIRMED = "reservation_confirmed", "确认订单"
        RESERVATION_CANCELLED = "reservation_cancelled", "取消订单"
        RESERVATION_CHECKED_IN = "reservation_checked_in", "办理入住"
        RESERVATION_CHECKED_OUT = "reservation_checked_out", "办理退房"
        RESERVATION_NO_SHOW = "reservation_no_show", "标记未到店"
        ROOM_CREATED = "room_created", "创建房间"
        ROOM_UPDATED = "room_updated", "修改房间"
        GUEST_CREATED = "guest_created", "创建客人"
        GUEST_UPDATED = "guest_updated", "修改客人"
        RESERVATION_NOTE_CREATED = (
            "reservation_note_created",
            "创建订单备注",
        )
        RESERVATION_NOTE_UPDATED = (
            "reservation_note_updated",
            "修改订单备注",
        )
        RESERVATION_NOTE_DELETED = (
            "reservation_note_deleted",
            "删除订单备注",
        )
        RESERVATION_NOTE_IMPORTANCE_CHANGED = (
            "reservation_note_importance_changed",
            "修改订单备注重要标记",
        )

    class TargetType(models.TextChoices):
        RESERVATION = "reservation", "订单"
        ROOM = "room", "房间"
        GUEST = "guest", "客人"
        RESERVATION_NOTE = "reservation_note", "订单备注"

    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admin_operation_logs",
    )
    action = models.CharField(max_length=40, choices=Action.choices, db_index=True)
    target_type = models.CharField(
        max_length=32,
        choices=TargetType.choices,
        db_index=True,
    )
    target_id = models.PositiveBigIntegerField(db_index=True)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["target_type", "target_id"],
                name="main_admin_log_target_idx",
            ),
        ]

    def __str__(self):
        return f"{self.get_action_display()} #{self.pk}"
