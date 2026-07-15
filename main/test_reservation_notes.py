from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from guest.models import Guest
from room.models import Room

from .forms import ReservationForm, ReservationNoteForm
from .models import AdminOperationLog, Reservation, ReservationNote
from .services import (
    create_reservation_note,
    delete_reservation_note,
    update_reservation_note,
)


def grant_permissions(user, *permission_names):
    permissions = []
    for permission_name in permission_names:
        app_label, codename = permission_name.split(".", 1)
        permissions.append(
            Permission.objects.get(
                content_type__app_label=app_label,
                codename=codename,
            )
        )
    user.user_permissions.add(*permissions)
    for cache_name in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
        user.__dict__.pop(cache_name, None)


class ReservationNoteTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        cls.room = Room.objects.create(
            room_number="NOTE-1",
            room_type="Test",
            price_per_night="100.00",
        )
        cls.other_room = Room.objects.create(
            room_number="NOTE-2",
            room_type="Test",
            price_per_night="100.00",
        )
        cls.guest = Guest.objects.create(
            first_name="SensitiveGuestName",
            last_name="PrivateLastName",
            email="note-guest@example.invalid",
            phone_number="13812345678",
            government_id="NOTE-ID-987654",
            address="Private note test address",
        )
        cls.reservation = Reservation.objects.create(
            room=cls.room,
            guest=cls.guest,
            additional="Private additional body",
            check_in_date=cls.today,
            check_out_date=cls.today + timedelta(days=2),
        )
        cls.other_reservation = Reservation.objects.create(
            room=cls.other_room,
            guest=cls.guest,
            check_in_date=cls.today,
            check_out_date=cls.today + timedelta(days=2),
        )

        user_model = get_user_model()
        cls.non_staff = user_model.objects.create_user(
            username="note-non-staff",
            password="test-password",
        )
        cls.staff_without_permissions = user_model.objects.create_user(
            username="note-no-permissions",
            password="test-password",
            is_staff=True,
        )
        cls.viewer = user_model.objects.create_user(
            username="note-viewer",
            password="test-password",
            is_staff=True,
        )
        cls.creator = user_model.objects.create_user(
            username="note-creator",
            password="test-password",
            is_staff=True,
        )
        cls.other_editor = user_model.objects.create_user(
            username="note-other-editor",
            password="test-password",
            is_staff=True,
        )
        cls.superuser = user_model.objects.create_superuser(
            username="note-superuser",
            email="note-superuser@example.invalid",
            password="test-password",
        )

        grant_permissions(
            cls.viewer,
            "main.view_reservation",
            "main.view_reservationnote",
        )
        grant_permissions(
            cls.creator,
            "main.view_reservation",
            "main.view_reservationnote",
            "main.add_reservationnote",
            "main.change_reservationnote",
        )
        grant_permissions(
            cls.other_editor,
            "main.view_reservation",
            "main.view_reservationnote",
            "main.change_reservationnote",
            "main.delete_reservationnote",
        )

    def make_note(self, **overrides):
        values = {
            "reservation": self.reservation,
            "content": "Internal note body",
            "created_by": self.creator,
        }
        values.update(overrides)
        return ReservationNote.objects.create(**values)

    def detail_url(self, reservation=None):
        reservation = reservation or self.reservation
        return reverse("reservation_detail", args=[reservation.pk])

    def create_url(self, reservation=None):
        reservation = reservation or self.reservation
        return reverse("reservation_note_create", args=[reservation.pk])

    def update_url(self, note, reservation=None):
        reservation = reservation or self.reservation
        return reverse(
            "reservation_note_update",
            args=[reservation.pk, note.pk],
        )

    def delete_url(self, note, reservation=None):
        reservation = reservation or self.reservation
        return reverse(
            "reservation_note_delete",
            args=[reservation.pk, note.pk],
        )


class ReservationNoteModelTests(ReservationNoteTestBase):
    def test_reservation_supports_multiple_notes_with_expected_defaults(self):
        first = self.make_note(content="First")
        second = self.make_note(content="Second")

        self.assertEqual(self.reservation.notes.count(), 2)
        self.assertEqual(first.reservation, self.reservation)
        self.assertFalse(first.is_important)
        self.assertIsNotNone(first.created_at)
        self.assertIsNotNone(first.updated_at)
        self.assertGreaterEqual(second.created_at, first.created_at)

    def test_deleted_creator_is_set_null_and_note_is_retained(self):
        note = self.make_note()
        self.creator.delete()

        note.refresh_from_db()
        self.assertIsNone(note.created_by)
        self.assertTrue(ReservationNote.objects.filter(pk=note.pk).exists())

    def test_notes_use_newest_first_ordering_and_indexes(self):
        first = self.make_note(content="First")
        second = self.make_note(content="Second")

        self.assertEqual(
            list(self.reservation.notes.values_list("pk", flat=True)),
            [second.pk, first.pk],
        )
        self.assertTrue(ReservationNote._meta.get_field("created_at").db_index)
        self.assertTrue(ReservationNote._meta.get_field("reservation").db_index)
        self.assertIn(
            ["reservation", "created_at"],
            [index.fields for index in ReservationNote._meta.indexes],
        )

    def test_additional_is_unchanged_and_is_not_converted_to_a_note(self):
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.additional, "Private additional body")
        self.assertFalse(self.reservation.notes.exists())
        self.assertIn("additional", ReservationForm().fields)


class ReservationNoteFormTests(ReservationNoteTestBase):
    def test_valid_content_is_trimmed_and_only_safe_fields_are_exposed(self):
        form = ReservationNoteForm(
            data={
                "content": "  Valid note  ",
                "is_important": "on",
                "reservation": self.other_reservation.pk,
                "created_by": self.other_editor.pk,
                "created_at": "2000-01-01",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["content"], "Valid note")
        self.assertTrue(form.cleaned_data["is_important"])
        self.assertEqual(set(form.fields), {"content", "is_important"})

    def test_empty_whitespace_and_newline_only_content_is_invalid(self):
        for content in ("", "   ", "\n\n\t"):
            with self.subTest(content=repr(content)):
                form = ReservationNoteForm(data={"content": content})
                self.assertFalse(form.is_valid())
                self.assertIn("content", form.errors)

    def test_content_over_5000_characters_is_invalid(self):
        form = ReservationNoteForm(data={"content": "x" * 5001})
        self.assertFalse(form.is_valid())
        self.assertIn("content", form.errors)

    def test_invalid_boolean_value_is_rejected(self):
        form = ReservationNoteForm(
            data={"content": "Valid", "is_important": "not-a-boolean"}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("is_important", form.errors)

    def test_html_is_preserved_as_text_for_template_autoescaping(self):
        content = '<script>alert("note")</script>'
        form = ReservationNoteForm(data={"content": content})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["content"], content)


class ReservationNoteServiceTests(ReservationNoteTestBase):
    def test_create_sets_server_owned_fields_and_writes_sanitized_log(self):
        body = "Highly sensitive internal note body"
        note = create_reservation_note(
            reservation_id=self.reservation.pk,
            content=f"  {body}  ",
            is_important=True,
            operator=self.creator,
        )

        self.assertEqual(note.reservation, self.reservation)
        self.assertEqual(note.created_by, self.creator)
        self.assertEqual(note.content, body)
        operation_log = AdminOperationLog.objects.get()
        self.assertEqual(
            operation_log.action,
            AdminOperationLog.Action.RESERVATION_NOTE_CREATED,
        )
        self.assertEqual(
            operation_log.target_type,
            AdminOperationLog.TargetType.RESERVATION_NOTE,
        )
        self.assertEqual(operation_log.target_id, note.pk)
        self.assertEqual(
            operation_log.description,
            f"Reservation note #{note.pk} was created for reservation "
            f"#{self.reservation.pk}.",
        )
        self.assertNotIn(body, operation_log.description)

    def test_create_permission_or_validation_failure_writes_no_log(self):
        with self.assertRaises(PermissionDenied):
            create_reservation_note(
                reservation_id=self.reservation.pk,
                content="Denied",
                is_important=False,
                operator=self.viewer,
            )
        with self.assertRaises(ValidationError):
            create_reservation_note(
                reservation_id=self.reservation.pk,
                content="   ",
                is_important=False,
                operator=self.creator,
            )
        self.assertFalse(ReservationNote.objects.exists())
        self.assertFalse(AdminOperationLog.objects.exists())

    def test_create_log_failure_rolls_back_note(self):
        with patch(
            "main.services.AdminOperationLog.objects.create",
            side_effect=RuntimeError("simulated log failure"),
        ):
            with self.assertRaises(RuntimeError):
                create_reservation_note(
                    reservation_id=self.reservation.pk,
                    content="Rollback this note",
                    is_important=False,
                    operator=self.creator,
                )
        self.assertFalse(ReservationNote.objects.exists())

    def test_update_reloads_note_updates_timestamp_and_logs_categories(self):
        note = self.make_note(content="Before")
        old_updated_at = note.updated_at
        updated_note, changed_fields = update_reservation_note(
            reservation_id=self.reservation.pk,
            note_id=note.pk,
            content="After",
            is_important=True,
            operator=self.creator,
        )

        updated_note.refresh_from_db()
        self.assertEqual(updated_note.content, "After")
        self.assertTrue(updated_note.is_important)
        self.assertGreater(updated_note.updated_at, old_updated_at)
        self.assertEqual(changed_fields, ("content", "is_important"))
        operation_log = AdminOperationLog.objects.get()
        self.assertEqual(
            operation_log.action,
            AdminOperationLog.Action.RESERVATION_NOTE_UPDATED,
        )
        self.assertEqual(
            operation_log.description,
            f"Reservation note #{note.pk} for reservation "
            f"#{self.reservation.pk} updated fields: content, importance.",
        )
        self.assertNotIn("Before", operation_log.description)
        self.assertNotIn("After", operation_log.description)

    def test_importance_only_update_uses_specific_action(self):
        note = self.make_note()
        update_reservation_note(
            reservation_id=self.reservation.pk,
            note_id=note.pk,
            content=note.content,
            is_important=True,
            operator=self.creator,
        )
        self.assertEqual(
            AdminOperationLog.objects.get().action,
            AdminOperationLog.Action.RESERVATION_NOTE_IMPORTANCE_CHANGED,
        )

    def test_unchanged_update_does_not_change_timestamp_or_write_log(self):
        note = self.make_note()
        old_updated_at = note.updated_at
        _, changed_fields = update_reservation_note(
            reservation_id=self.reservation.pk,
            note_id=note.pk,
            content=f"  {note.content}  ",
            is_important=note.is_important,
            operator=self.creator,
        )

        note.refresh_from_db()
        self.assertEqual(changed_fields, ())
        self.assertEqual(note.updated_at, old_updated_at)
        self.assertFalse(AdminOperationLog.objects.exists())

    def test_update_log_failure_rolls_back_note_changes(self):
        note = self.make_note(content="Original content")
        with patch(
            "main.services.AdminOperationLog.objects.create",
            side_effect=RuntimeError("simulated log failure"),
        ):
            with self.assertRaises(RuntimeError):
                update_reservation_note(
                    reservation_id=self.reservation.pk,
                    note_id=note.pk,
                    content="Must be rolled back",
                    is_important=True,
                    operator=self.creator,
                )

        note.refresh_from_db()
        self.assertEqual(note.content, "Original content")
        self.assertFalse(note.is_important)
        self.assertFalse(AdminOperationLog.objects.exists())

    def test_update_requires_owner_and_matching_reservation(self):
        note = self.make_note()
        with self.assertRaises(PermissionDenied):
            update_reservation_note(
                reservation_id=self.reservation.pk,
                note_id=note.pk,
                content="Denied",
                is_important=False,
                operator=self.other_editor,
            )
        with self.assertRaises(ReservationNote.DoesNotExist):
            update_reservation_note(
                reservation_id=self.other_reservation.pk,
                note_id=note.pk,
                content="Wrong reservation",
                is_important=False,
                operator=self.creator,
            )
        note.refresh_from_db()
        self.assertEqual(note.content, "Internal note body")
        self.assertFalse(AdminOperationLog.objects.exists())

    def test_superuser_can_update_note_after_creator_is_deleted(self):
        note = self.make_note()
        self.creator.delete()
        update_reservation_note(
            reservation_id=self.reservation.pk,
            note_id=note.pk,
            content="Superuser update",
            is_important=False,
            operator=self.superuser,
        )
        note.refresh_from_db()
        self.assertIsNone(note.created_by)
        self.assertEqual(note.content, "Superuser update")

    def test_only_superuser_can_delete_even_with_delete_permission(self):
        note = self.make_note()
        with self.assertRaises(PermissionDenied):
            delete_reservation_note(
                reservation_id=self.reservation.pk,
                note_id=note.pk,
                operator=self.other_editor,
            )
        self.assertTrue(ReservationNote.objects.filter(pk=note.pk).exists())
        self.assertFalse(AdminOperationLog.objects.exists())

    def test_delete_writes_log_after_note_is_removed(self):
        note = self.make_note(content="Never copy this deleted body")
        note_id = note.pk
        delete_reservation_note(
            reservation_id=self.reservation.pk,
            note_id=note.pk,
            operator=self.superuser,
        )

        self.assertFalse(ReservationNote.objects.filter(pk=note_id).exists())
        operation_log = AdminOperationLog.objects.get()
        self.assertEqual(
            operation_log.action,
            AdminOperationLog.Action.RESERVATION_NOTE_DELETED,
        )
        self.assertEqual(operation_log.target_id, note_id)
        self.assertEqual(
            operation_log.description,
            f"Reservation note #{note_id} was deleted from reservation "
            f"#{self.reservation.pk}.",
        )
        self.assertNotIn("Never copy", operation_log.description)

    def test_delete_log_failure_rolls_back_deletion(self):
        note = self.make_note()
        with patch(
            "main.services.AdminOperationLog.objects.create",
            side_effect=RuntimeError("simulated log failure"),
        ):
            with self.assertRaises(RuntimeError):
                delete_reservation_note(
                    reservation_id=self.reservation.pk,
                    note_id=note.pk,
                    operator=self.superuser,
                )
        self.assertTrue(ReservationNote.objects.filter(pk=note.pk).exists())

    def test_note_logs_never_include_guest_or_reservation_sensitive_values(self):
        secret_body = "Secret note fragment 987"
        note = create_reservation_note(
            reservation_id=self.reservation.pk,
            content=secret_body,
            is_important=False,
            operator=self.creator,
        )
        update_reservation_note(
            reservation_id=self.reservation.pk,
            note_id=note.pk,
            content="Replacement secret body",
            is_important=False,
            operator=self.creator,
        )
        delete_reservation_note(
            reservation_id=self.reservation.pk,
            note_id=note.pk,
            operator=self.superuser,
        )

        descriptions = " ".join(
            AdminOperationLog.objects.values_list("description", flat=True)
        )
        for sensitive_value in (
            secret_body,
            "Replacement secret body",
            self.guest.first_name,
            self.guest.last_name,
            self.guest.phone_number,
            self.guest.government_id,
            self.guest.address,
            self.reservation.additional,
        ):
            with self.subTest(value=sensitive_value):
                self.assertNotIn(sensitive_value, descriptions)


class ReservationNoteViewPermissionTests(ReservationNoteTestBase):
    def test_anonymous_and_non_staff_users_cannot_view_internal_notes(self):
        note = self.make_note()
        anonymous_response = self.client.get(self.detail_url())
        self.assertEqual(anonymous_response.status_code, 302)
        self.assertIn(reverse("login"), anonymous_response.url)

        grant_permissions(
            self.non_staff,
            "main.view_reservation",
            "main.view_reservationnote",
        )
        self.client.force_login(self.non_staff)
        response = self.client.get(self.detail_url())
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, note.content, status_code=403)

    def test_staff_without_note_view_permission_sees_order_but_not_note_area(self):
        note = self.make_note()
        grant_permissions(
            self.staff_without_permissions,
            "main.view_reservation",
        )
        self.client.force_login(self.staff_without_permissions)
        response = self.client.get(self.detail_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "内部备注")
        self.assertNotContains(response, note.content)

    def test_note_view_permission_without_reservation_view_is_rejected(self):
        grant_permissions(
            self.staff_without_permissions,
            "main.view_reservationnote",
        )
        self.client.force_login(self.staff_without_permissions)
        response = self.client.get(self.detail_url())
        self.assertEqual(response.status_code, 403)

    def test_fully_authorized_staff_and_superuser_can_view_notes(self):
        note = self.make_note()
        for user in (self.viewer, self.superuser):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(self.detail_url())
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "内部备注")
                self.assertContains(response, note.content)

    def test_edit_url_cannot_cross_reservation_boundary(self):
        note = self.make_note()
        self.client.force_login(self.creator)
        response = self.client.get(
            self.update_url(note, reservation=self.other_reservation)
        )
        self.assertEqual(response.status_code, 404)


class ReservationNoteCreateViewTests(ReservationNoteTestBase):
    def test_anonymous_non_staff_and_unauthorized_staff_cannot_create(self):
        anonymous = self.client.post(
            self.create_url(), {"content": "Anonymous"}
        )
        self.assertEqual(anonymous.status_code, 302)

        grant_permissions(
            self.non_staff,
            "main.view_reservation",
            "main.add_reservationnote",
        )
        self.client.force_login(self.non_staff)
        self.assertEqual(
            self.client.post(self.create_url(), {"content": "Non-staff"}).status_code,
            403,
        )

        self.client.force_login(self.viewer)
        self.assertEqual(
            self.client.post(self.create_url(), {"content": "No add"}).status_code,
            403,
        )
        self.assertFalse(ReservationNote.objects.exists())

    def test_create_page_displays_only_reservation_id_and_safe_form_fields(self):
        self.client.force_login(self.creator)
        response = self.client.get(self.create_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"所属订单：#{self.reservation.pk}")
        for sensitive_value in (
            self.guest.first_name,
            self.guest.phone_number,
            self.guest.government_id,
            self.guest.address,
        ):
            self.assertNotContains(response, sensitive_value)

    def test_authorized_post_uses_url_reservation_and_authenticated_creator(self):
        self.client.force_login(self.creator)
        response = self.client.post(
            self.create_url(),
            {
                "content": "Created through view",
                "is_important": "on",
                "reservation": self.other_reservation.pk,
                "created_by": self.other_editor.pk,
            },
        )

        self.assertRedirects(response, self.detail_url())
        note = ReservationNote.objects.get()
        self.assertEqual(note.reservation, self.reservation)
        self.assertEqual(note.created_by, self.creator)
        self.assertTrue(note.is_important)
        self.assertEqual(
            AdminOperationLog.objects.get().action,
            AdminOperationLog.Action.RESERVATION_NOTE_CREATED,
        )

    def test_invalid_create_does_not_write_note_or_log(self):
        self.client.force_login(self.creator)
        response = self.client.post(self.create_url(), {"content": "  \n "})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "备注内容不能为空")
        self.assertFalse(ReservationNote.objects.exists())
        self.assertFalse(AdminOperationLog.objects.exists())

    def test_create_post_is_csrf_protected(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.creator)
        response = csrf_client.post(
            self.create_url(), {"content": "No CSRF"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(ReservationNote.objects.exists())


class ReservationNoteUpdateViewTests(ReservationNoteTestBase):
    def test_creator_with_change_permission_can_update_own_note(self):
        note = self.make_note(content="Before")
        self.client.force_login(self.creator)
        response = self.client.post(
            self.update_url(note),
            {"content": "After", "is_important": "on"},
        )

        self.assertRedirects(response, self.detail_url())
        note.refresh_from_db()
        self.assertEqual(note.content, "After")
        self.assertTrue(note.is_important)
        self.assertEqual(AdminOperationLog.objects.count(), 1)

    def test_creator_without_change_permission_and_other_editor_are_rejected(self):
        viewer_note = self.make_note(created_by=self.viewer)
        self.client.force_login(self.viewer)
        response = self.client.post(
            self.update_url(viewer_note), {"content": "Denied"}
        )
        self.assertEqual(response.status_code, 403)

        creator_note = self.make_note(content="Original")
        self.client.force_login(self.other_editor)
        response = self.client.post(
            self.update_url(creator_note), {"content": "Also denied"}
        )
        self.assertEqual(response.status_code, 403)
        creator_note.refresh_from_db()
        self.assertEqual(creator_note.content, "Original")
        self.assertFalse(AdminOperationLog.objects.exists())

    def test_superuser_can_update_another_users_note(self):
        note = self.make_note()
        self.client.force_login(self.superuser)
        response = self.client.post(
            self.update_url(note), {"content": "Superuser edited"}
        )
        self.assertRedirects(response, self.detail_url())
        note.refresh_from_db()
        self.assertEqual(note.content, "Superuser edited")

    def test_unchanged_post_returns_without_update_log(self):
        note = self.make_note()
        self.client.force_login(self.creator)
        response = self.client.post(
            self.update_url(note),
            {"content": f"  {note.content}  "},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "内部备注没有变化")
        self.assertFalse(AdminOperationLog.objects.exists())

    def test_invalid_update_writes_no_log(self):
        note = self.make_note()
        self.client.force_login(self.creator)
        response = self.client.post(
            self.update_url(note), {"content": "\n\n"}
        )
        self.assertEqual(response.status_code, 200)
        note.refresh_from_db()
        self.assertEqual(note.content, "Internal note body")
        self.assertFalse(AdminOperationLog.objects.exists())

    def test_update_post_is_csrf_protected(self):
        note = self.make_note()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.creator)
        response = csrf_client.post(
            self.update_url(note), {"content": "No CSRF"}
        )
        self.assertEqual(response.status_code, 403)
        note.refresh_from_db()
        self.assertEqual(note.content, "Internal note body")


class ReservationNoteDeleteViewTests(ReservationNoteTestBase):
    def test_regular_staff_cannot_delete_even_with_delete_permission(self):
        note = self.make_note()
        self.client.force_login(self.other_editor)
        for method in (self.client.get, self.client.post):
            with self.subTest(method=method.__name__):
                response = method(self.delete_url(note))
                self.assertEqual(response.status_code, 403)
        self.assertTrue(ReservationNote.objects.filter(pk=note.pk).exists())
        self.assertFalse(AdminOperationLog.objects.exists())

    def test_delete_get_is_confirmation_only_and_hides_content(self):
        secret_content = "Do not show this body on delete confirmation"
        note = self.make_note(content=secret_content, is_important=True)
        self.client.force_login(self.superuser)
        response = self.client.get(self.delete_url(note))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"备注ID：#{note.pk}")
        self.assertContains(response, f"所属订单：#{self.reservation.pk}")
        self.assertNotContains(response, secret_content)
        self.assertTrue(ReservationNote.objects.filter(pk=note.pk).exists())
        self.assertFalse(AdminOperationLog.objects.exists())

    def test_superuser_post_deletes_and_repeat_does_not_duplicate_log(self):
        note = self.make_note()
        delete_url = self.delete_url(note)
        self.client.force_login(self.superuser)
        response = self.client.post(delete_url)
        self.assertRedirects(response, self.detail_url())
        self.assertFalse(ReservationNote.objects.filter(pk=note.pk).exists())
        self.assertEqual(
            AdminOperationLog.objects.filter(
                action=AdminOperationLog.Action.RESERVATION_NOTE_DELETED
            ).count(),
            1,
        )

        repeated = self.client.post(delete_url)
        self.assertEqual(repeated.status_code, 404)
        self.assertEqual(
            AdminOperationLog.objects.filter(
                action=AdminOperationLog.Action.RESERVATION_NOTE_DELETED
            ).count(),
            1,
        )

    def test_delete_post_is_csrf_protected(self):
        note = self.make_note()
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.superuser)
        response = csrf_client.post(self.delete_url(note))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(ReservationNote.objects.filter(pk=note.pk).exists())


class ReservationNoteDisplayTests(ReservationNoteTestBase):
    def test_empty_state_and_button_visibility_follow_permissions(self):
        self.client.force_login(self.viewer)
        viewer_response = self.client.get(self.detail_url())
        self.assertContains(viewer_response, "暂无内部备注")
        self.assertNotContains(viewer_response, "添加内部备注")
        self.assertNotContains(viewer_response, "编辑备注")
        self.assertNotContains(viewer_response, "删除备注")

        note = self.make_note()
        self.client.force_login(self.creator)
        creator_response = self.client.get(self.detail_url())
        self.assertContains(creator_response, "添加内部备注")
        self.assertContains(creator_response, "编辑备注")
        self.assertNotContains(creator_response, "删除备注")

        self.client.force_login(self.superuser)
        superuser_response = self.client.get(self.detail_url())
        self.assertContains(superuser_response, "删除备注")
        self.assertContains(superuser_response, note.content)

    def test_important_label_is_textual_and_absent_for_normal_note(self):
        normal_note = self.make_note(is_important=False)
        self.client.force_login(self.viewer)
        normal_response = self.client.get(self.detail_url())
        self.assertNotContains(normal_response, 'aria-label="重要备注"')

        normal_note.is_important = True
        normal_note.save(update_fields=["is_important"])
        important_response = self.client.get(self.detail_url())
        self.assertContains(important_response, 'aria-label="重要备注"')
        self.assertContains(important_response, ">重要<")

    def test_deleted_creator_is_displayed_as_deleted_user(self):
        self.make_note()
        self.creator.delete()
        self.client.force_login(self.viewer)
        response = self.client.get(self.detail_url())
        self.assertContains(response, "已删除用户")

    def test_notes_are_displayed_newest_first(self):
        first = self.make_note(content="Older unique note")
        second = self.make_note(content="Newer unique note")
        self.client.force_login(self.viewer)
        response = self.client.get(self.detail_url())
        body = response.content.decode()
        self.assertLess(body.index(second.content), body.index(first.content))

    def test_newlines_are_preserved_and_script_is_escaped(self):
        self.make_note(
            content='Line one\nLine two\n<script>alert("unsafe")</script>'
        )
        self.client.force_login(self.viewer)
        response = self.client.get(self.detail_url())
        self.assertContains(response, "Line one<br>Line two")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, '<script>alert("unsafe")</script>')


class ReservationNoteAdminTests(ReservationNoteTestBase):
    def test_admin_is_read_only_even_for_superuser(self):
        note_admin = admin.site._registry[ReservationNote]
        request = SimpleNamespace(user=self.superuser)

        self.assertFalse(note_admin.has_add_permission(request))
        self.assertFalse(note_admin.has_change_permission(request))
        self.assertFalse(note_admin.has_delete_permission(request))
        self.assertNotIn("content", note_admin.list_display)
        self.assertEqual(note_admin.search_fields, ("=reservation__id",))
        self.assertIn("is_important", note_admin.list_filter)

    def test_admin_changelist_does_not_display_note_content(self):
        note = self.make_note(content="Admin list must hide this full content")
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:main_reservationnote_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(note.pk))
        self.assertNotContains(response, note.content)

    def test_operation_log_admin_remains_immutable(self):
        log_admin = admin.site._registry[AdminOperationLog]
        request = SimpleNamespace(user=self.superuser)
        self.assertFalse(log_admin.has_add_permission(request))
        self.assertFalse(log_admin.has_change_permission(request))
        self.assertFalse(log_admin.has_delete_permission(request))
