from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from room.models import Room

from .models import AdminOperationLog, Reservation, ReservationNote


class ReservationTransitionError(Exception):
    """Raised when a requested reservation status transition is not allowed."""


def _is_staff_user(user):
    return bool(user and user.is_authenticated and user.is_staff)


def can_view_reservation_notes(user):
    return _is_staff_user(user) and user.has_perms(
        ("main.view_reservation", "main.view_reservationnote")
    )


def can_add_reservation_notes(user):
    return _is_staff_user(user) and user.has_perms(
        ("main.view_reservation", "main.add_reservationnote")
    )


def can_edit_reservation_note(user, note):
    if not _is_staff_user(user):
        return False
    if user.is_superuser:
        return True
    return (
        can_view_reservation_notes(user)
        and user.has_perm("main.change_reservationnote")
        and note.created_by_id == user.pk
    )


def can_delete_reservation_note(user):
    return _is_staff_user(user) and user.is_superuser


ALLOWED_TRANSITIONS = {
    Reservation.Status.PENDING: (
        Reservation.Status.CONFIRMED,
        Reservation.Status.CANCELLED,
        Reservation.Status.NO_SHOW,
    ),
    Reservation.Status.CONFIRMED: (
        Reservation.Status.CHECKED_IN,
        Reservation.Status.CANCELLED,
        Reservation.Status.NO_SHOW,
    ),
    Reservation.Status.CHECKED_IN: (Reservation.Status.CHECKED_OUT,),
    Reservation.Status.CHECKED_OUT: (),
    Reservation.Status.CANCELLED: (),
    Reservation.Status.NO_SHOW: (),
}

TRANSITION_ACTIONS = {
    Reservation.Status.CONFIRMED: AdminOperationLog.Action.RESERVATION_CONFIRMED,
    Reservation.Status.CANCELLED: AdminOperationLog.Action.RESERVATION_CANCELLED,
    Reservation.Status.CHECKED_IN: AdminOperationLog.Action.RESERVATION_CHECKED_IN,
    Reservation.Status.CHECKED_OUT: AdminOperationLog.Action.RESERVATION_CHECKED_OUT,
    Reservation.Status.NO_SHOW: AdminOperationLog.Action.RESERVATION_NO_SHOW,
}


def _status_label(status):
    return Reservation.Status(status).label


def _validate_transition(reservation, target_status, business_date):
    if reservation.status == target_status:
        raise ReservationTransitionError(
            f"Reservation #{reservation.pk} is already {_status_label(target_status)}."
        )

    allowed_targets = ALLOWED_TRANSITIONS.get(reservation.status, ())
    if target_status not in allowed_targets:
        raise ReservationTransitionError(
            f"Reservation #{reservation.pk} cannot change from "
            f"{_status_label(reservation.status)} to {_status_label(target_status)}."
        )

    if target_status == Reservation.Status.CHECKED_IN:
        if business_date < reservation.check_in_date:
            raise ReservationTransitionError(
                "Check-in is not allowed before the reservation check-in date."
            )
        if business_date >= reservation.check_out_date:
            raise ReservationTransitionError(
                "Normal check-in is not allowed on or after the check-out date."
            )

    if target_status == Reservation.Status.NO_SHOW:
        if business_date < reservation.check_in_date:
            raise ReservationTransitionError(
                "A reservation cannot be marked no-show before its check-in date."
            )


def get_allowed_transitions(reservation, business_date=None):
    """Return currently legal target statuses without changing the reservation."""
    business_date = business_date or timezone.localdate()
    allowed = []
    for target_status in ALLOWED_TRANSITIONS.get(reservation.status, ()):
        try:
            _validate_transition(reservation, target_status, business_date)
        except ReservationTransitionError:
            continue
        allowed.append(target_status)
    return allowed


def create_operation_log(
    *, operator, action, target_type, target_id, description
):
    """Create a deliberately non-sensitive audit entry.

    Callers that modify business data must call this inside the same atomic
    transaction as that modification.
    """
    return AdminOperationLog.objects.create(
        operator=operator,
        action=action,
        target_type=target_type,
        target_id=target_id,
        description=description,
    )


@transaction.atomic
def create_reservation_note(
    *, reservation_id, content, is_important, operator
):
    if not can_add_reservation_notes(operator):
        raise PermissionDenied("没有添加订单备注的权限。")
    if type(is_important) is not bool:
        raise ValidationError({"is_important": "必须提供有效的布尔值。"})

    reservation = Reservation.objects.select_for_update().get(pk=reservation_id)
    note = ReservationNote(
        reservation=reservation,
        content=content.strip() if isinstance(content, str) else "",
        is_important=is_important,
        created_by=operator,
    )
    note.full_clean()
    note.save()
    create_operation_log(
        operator=operator,
        action=AdminOperationLog.Action.RESERVATION_NOTE_CREATED,
        target_type=AdminOperationLog.TargetType.RESERVATION_NOTE,
        target_id=note.pk,
        description=(
            f"Reservation note #{note.pk} was created for "
            f"reservation #{reservation.pk}."
        ),
    )
    return note


@transaction.atomic
def update_reservation_note(
    *, reservation_id, note_id, content, is_important, operator
):
    if type(is_important) is not bool:
        raise ValidationError({"is_important": "必须提供有效的布尔值。"})

    note = (
        ReservationNote.objects.select_for_update()
        .select_related("reservation", "created_by")
        .get(pk=note_id, reservation_id=reservation_id)
    )
    if not can_edit_reservation_note(operator, note):
        raise PermissionDenied("没有修改该订单备注的权限。")

    normalized_content = content.strip() if isinstance(content, str) else ""
    changed_fields = []
    if note.content != normalized_content:
        note.content = normalized_content
        changed_fields.append("content")
    if note.is_important != is_important:
        note.is_important = is_important
        changed_fields.append("is_important")

    note.full_clean()
    if not changed_fields:
        return note, ()

    note.save(update_fields=[*changed_fields, "updated_at"])
    categories = [
        "importance" if field == "is_important" else field
        for field in changed_fields
    ]
    action = (
        AdminOperationLog.Action.RESERVATION_NOTE_IMPORTANCE_CHANGED
        if changed_fields == ["is_important"]
        else AdminOperationLog.Action.RESERVATION_NOTE_UPDATED
    )
    create_operation_log(
        operator=operator,
        action=action,
        target_type=AdminOperationLog.TargetType.RESERVATION_NOTE,
        target_id=note.pk,
        description=(
            f"Reservation note #{note.pk} for reservation "
            f"#{note.reservation_id} updated fields: {', '.join(categories)}."
        ),
    )
    return note, tuple(changed_fields)


@transaction.atomic
def delete_reservation_note(*, reservation_id, note_id, operator):
    note = (
        ReservationNote.objects.select_for_update()
        .select_related("reservation")
        .get(pk=note_id, reservation_id=reservation_id)
    )
    if not can_delete_reservation_note(operator):
        raise PermissionDenied("只有超级管理员可以删除订单备注。")

    deleted_note_id = note.pk
    target_reservation_id = note.reservation_id
    note.delete()
    create_operation_log(
        operator=operator,
        action=AdminOperationLog.Action.RESERVATION_NOTE_DELETED,
        target_type=AdminOperationLog.TargetType.RESERVATION_NOTE,
        target_id=deleted_note_id,
        description=(
            f"Reservation note #{deleted_note_id} was deleted from "
            f"reservation #{target_reservation_id}."
        ),
    )
    return target_reservation_id


@transaction.atomic
def transition_reservation(
    *, reservation_id, target_status, operator, business_date=None
):
    """Validate, lock, transition, and audit one reservation atomically."""
    try:
        target_status = Reservation.Status(target_status)
    except ValueError as exc:
        raise ReservationTransitionError("Unknown reservation target status.") from exc
    business_date = business_date or timezone.localdate()
    reservation = (
        Reservation.objects.select_for_update()
        .select_related("room")
        .get(pk=reservation_id)
    )
    _validate_transition(reservation, target_status, business_date)

    # Lock the room and re-read active reservations before a status change.
    # SQLite accepts these calls but does not provide row-level SELECT FOR
    # UPDATE locking; production concurrency still needs a capable database.
    Room.objects.select_for_update().get(pk=reservation.room_id)
    list(
        Reservation.objects.select_for_update()
        .filter(
            room_id=reservation.room_id,
            status__in=Reservation.OCCUPYING_STATUSES,
        )
        .exclude(pk=reservation.pk)
        .order_by("pk")
        .values_list("pk", flat=True)
    )

    previous_status = reservation.status
    reservation.status = target_status
    try:
        reservation.full_clean()
    except ValidationError as exc:
        raise ReservationTransitionError(
            "The reservation could not be transitioned because its booking "
            "data is no longer valid."
        ) from exc
    reservation.save(update_fields=["status"])

    create_operation_log(
        operator=operator,
        action=TRANSITION_ACTIONS[target_status],
        target_type=AdminOperationLog.TargetType.RESERVATION,
        target_id=reservation.pk,
        description=(
            f"Reservation #{reservation.pk} changed from "
            f"{previous_status} to {target_status}."
        ),
    )
    return reservation


def confirm_reservation(*, reservation_id, operator, business_date=None):
    return transition_reservation(
        reservation_id=reservation_id,
        target_status=Reservation.Status.CONFIRMED,
        operator=operator,
        business_date=business_date,
    )


def cancel_reservation(*, reservation_id, operator, business_date=None):
    return transition_reservation(
        reservation_id=reservation_id,
        target_status=Reservation.Status.CANCELLED,
        operator=operator,
        business_date=business_date,
    )


def check_in_reservation(*, reservation_id, operator, business_date=None):
    return transition_reservation(
        reservation_id=reservation_id,
        target_status=Reservation.Status.CHECKED_IN,
        operator=operator,
        business_date=business_date,
    )


def check_out_reservation(*, reservation_id, operator, business_date=None):
    return transition_reservation(
        reservation_id=reservation_id,
        target_status=Reservation.Status.CHECKED_OUT,
        operator=operator,
        business_date=business_date,
    )


def mark_reservation_no_show(*, reservation_id, operator, business_date=None):
    return transition_reservation(
        reservation_id=reservation_id,
        target_status=Reservation.Status.NO_SHOW,
        operator=operator,
        business_date=business_date,
    )


def reservation_change_categories(changed_fields):
    categories = []
    changed_fields = set(changed_fields)
    if "room" in changed_fields:
        categories.append("room")
    if "guest" in changed_fields:
        categories.append("guest")
    if {"check_in_date", "check_out_date"} & changed_fields:
        categories.append("dates")
    if "additional" in changed_fields:
        categories.append("additional")
    return categories


def log_reservation_created(*, operator, reservation):
    return create_operation_log(
        operator=operator,
        action=AdminOperationLog.Action.RESERVATION_CREATED,
        target_type=AdminOperationLog.TargetType.RESERVATION,
        target_id=reservation.pk,
        description=f"Reservation #{reservation.pk} created.",
    )


def log_reservation_updated(*, operator, reservation, changed_fields):
    categories = reservation_change_categories(changed_fields)
    if not categories:
        return None
    return create_operation_log(
        operator=operator,
        action=AdminOperationLog.Action.RESERVATION_UPDATED,
        target_type=AdminOperationLog.TargetType.RESERVATION,
        target_id=reservation.pk,
        description=(
            f"Reservation #{reservation.pk} updated fields: "
            f"{', '.join(categories)}."
        ),
    )


def log_room_created(*, operator, room):
    return create_operation_log(
        operator=operator,
        action=AdminOperationLog.Action.ROOM_CREATED,
        target_type=AdminOperationLog.TargetType.ROOM,
        target_id=room.pk,
        description=f"Room #{room.pk} created.",
    )


def log_room_updated(*, operator, room):
    return create_operation_log(
        operator=operator,
        action=AdminOperationLog.Action.ROOM_UPDATED,
        target_type=AdminOperationLog.TargetType.ROOM,
        target_id=room.pk,
        description=f"Room #{room.pk} updated.",
    )


def log_guest_created(*, operator, guest):
    return create_operation_log(
        operator=operator,
        action=AdminOperationLog.Action.GUEST_CREATED,
        target_type=AdminOperationLog.TargetType.GUEST,
        target_id=guest.pk,
        description=f"Guest #{guest.pk} created.",
    )


def log_guest_updated(*, operator, guest):
    return create_operation_log(
        operator=operator,
        action=AdminOperationLog.Action.GUEST_UPDATED,
        target_type=AdminOperationLog.TargetType.GUEST,
        target_id=guest.pk,
        description=f"Guest #{guest.pk} updated.",
    )
