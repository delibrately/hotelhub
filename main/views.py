from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.mixins import (
    PreserveQueryStringMixin,
    StaffPermissionRequiredMixin,
    StaffRequiredMixin,
)
from guest.models import Guest
from room.models import Room

from .forms import ReservationForm, ReservationNoteForm
from .models import AdminOperationLog, Reservation, ReservationNote
from .services import (
    ReservationTransitionError,
    cancel_reservation,
    can_add_reservation_notes,
    can_delete_reservation_note,
    can_edit_reservation_note,
    can_view_reservation_notes,
    check_in_reservation,
    check_out_reservation,
    confirm_reservation,
    create_reservation_note,
    delete_reservation_note,
    get_allowed_transitions,
    log_reservation_created,
    log_reservation_updated,
    mark_reservation_no_show,
    update_reservation_note,
)


STATUS_ACTION_PRESENTATION = {
    Reservation.Status.CONFIRMED: {
        "label": "确认订单",
        "url_name": "reservation_confirm",
    },
    Reservation.Status.CANCELLED: {
        "label": "取消订单",
        "url_name": "reservation_cancel",
    },
    Reservation.Status.CHECKED_IN: {
        "label": "办理入住",
        "url_name": "reservation_check_in",
    },
    Reservation.Status.CHECKED_OUT: {
        "label": "办理退房",
        "url_name": "reservation_check_out",
    },
    Reservation.Status.NO_SHOW: {
        "label": "标记未到店",
        "url_name": "reservation_no_show",
    },
}


class ModdView(View):
    def get(self, request):
        return render(request, "modd.html")


class DashboardView(StaffRequiredMixin, View):
    def get(self, request):
        can_view_rooms = request.user.has_perm("room.view_room")
        can_view_guests = request.user.has_perm("guest.view_guest")
        can_view_reservations = request.user.has_perm("main.view_reservation")
        context = {
            "can_view_rooms": can_view_rooms,
            "can_view_guests": can_view_guests,
            "can_view_reservations": can_view_reservations,
            "total_rooms": Room.objects.count() if can_view_rooms else None,
            "total_guests": Guest.objects.count() if can_view_guests else None,
            "total_reservations": (
                Reservation.objects.count() if can_view_reservations else None
            ),
            "pending_reservations": None,
            "confirmed_reservations": None,
            "today_check_ins": None,
            "today_check_outs": None,
            "current_checked_in": None,
        }
        if can_view_reservations:
            today = timezone.localdate()
            reservations = Reservation.objects.all()
            context.update(
                {
                    "pending_reservations": reservations.filter(
                        status=Reservation.Status.PENDING
                    ).count(),
                    "confirmed_reservations": reservations.filter(
                        status=Reservation.Status.CONFIRMED
                    ).count(),
                    "today_check_ins": reservations.filter(
                        status=Reservation.Status.CONFIRMED,
                        check_in_date=today,
                    ).count(),
                    "today_check_outs": reservations.filter(
                        status=Reservation.Status.CHECKED_IN,
                        check_out_date=today,
                    ).count(),
                    "current_checked_in": reservations.filter(
                        status=Reservation.Status.CHECKED_IN
                    ).count(),
                }
            )
        return render(request, "dashboard.html", context)


class ReservationCreateView(StaffPermissionRequiredMixin, CreateView):
    model = Reservation
    template_name = "form.html"
    form_class = ReservationForm
    permission_required = "main.add_reservation"

    def get_initial(self):
        initial = super().get_initial()
        guest_id = self.request.GET.get("guest_id")
        if guest_id:
            initial["guest"] = guest_id
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Reservation"
        return context

    @transaction.atomic
    def form_valid(self, form):
        response = super().form_valid(form)
        log_reservation_created(
            operator=self.request.user,
            reservation=self.object,
        )
        return response


class ReservationUpdateView(StaffPermissionRequiredMixin, UpdateView):
    model = Reservation
    template_name = "form.html"
    form_class = ReservationForm
    permission_required = "main.change_reservation"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Update Reservation"
        return context

    @transaction.atomic
    def form_valid(self, form):
        changed_fields = list(form.changed_data)
        response = super().form_valid(form)
        log_reservation_updated(
            operator=self.request.user,
            reservation=self.object,
            changed_fields=changed_fields,
        )
        return response


class ReservationDetailView(StaffPermissionRequiredMixin, DetailView):
    model = Reservation
    template_name = "reservation_detail.html"
    permission_required = "main.view_reservation"

    def get_queryset(self):
        queryset = super().get_queryset().select_related("room", "guest")
        if can_view_reservation_notes(self.request.user):
            queryset = queryset.prefetch_related(
                Prefetch(
                    "notes",
                    queryset=ReservationNote.objects.select_related(
                        "created_by"
                    ).order_by("-created_at", "-id"),
                )
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        can_manage_status = self.request.user.has_perms(
            ("main.view_reservation", "main.manage_reservation_status")
        )
        status_actions = []
        if can_manage_status:
            for target_status in get_allowed_transitions(self.object):
                presentation = STATUS_ACTION_PRESENTATION[target_status]
                status_actions.append(
                    {
                        "label": presentation["label"],
                        "url": reverse(
                            presentation["url_name"], args=[self.object.pk]
                        ),
                    }
                )
        context["can_manage_status"] = can_manage_status
        context["status_actions"] = status_actions
        can_view_notes = can_view_reservation_notes(self.request.user)
        context["can_view_reservation_notes"] = can_view_notes
        context["can_add_reservation_notes"] = (
            can_view_notes and can_add_reservation_notes(self.request.user)
        )
        context["can_delete_reservation_notes"] = can_delete_reservation_note(
            self.request.user
        )
        context["reservation_note_rows"] = []
        if can_view_notes:
            context["reservation_note_rows"] = [
                {
                    "note": note,
                    "can_edit": can_edit_reservation_note(
                        self.request.user, note
                    ),
                }
                for note in self.object.notes.all()
            ]
        return context


class ReservationNoteCreateView(StaffPermissionRequiredMixin, View):
    permission_required = (
        "main.view_reservation",
        "main.add_reservationnote",
    )
    template_name = "reservation_note_form.html"

    def get_reservation(self, reservation_pk):
        return get_object_or_404(Reservation, pk=reservation_pk)

    def render_form(self, request, reservation, form):
        return render(
            request,
            self.template_name,
            {
                "reservation": reservation,
                "form": form,
                "title": "添加内部备注",
                "submit_label": "添加备注",
            },
        )

    def get(self, request, reservation_pk):
        reservation = self.get_reservation(reservation_pk)
        return self.render_form(request, reservation, ReservationNoteForm())

    def post(self, request, reservation_pk):
        reservation = self.get_reservation(reservation_pk)
        form = ReservationNoteForm(request.POST)
        if form.is_valid():
            try:
                create_reservation_note(
                    reservation_id=reservation.pk,
                    content=form.cleaned_data["content"],
                    is_important=form.cleaned_data["is_important"],
                    operator=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, "内部备注已添加。")
                return redirect("reservation_detail", pk=reservation.pk)
        return self.render_form(request, reservation, form)


class ReservationNoteUpdateView(StaffPermissionRequiredMixin, View):
    permission_required = (
        "main.view_reservation",
        "main.view_reservationnote",
        "main.change_reservationnote",
    )
    template_name = "reservation_note_form.html"

    def get_note(self, reservation_pk, note_pk):
        note = get_object_or_404(
            ReservationNote.objects.select_related("reservation", "created_by"),
            pk=note_pk,
            reservation_id=reservation_pk,
        )
        if not can_edit_reservation_note(self.request.user, note):
            raise PermissionDenied
        return note

    def render_form(self, request, note, form):
        return render(
            request,
            self.template_name,
            {
                "reservation": note.reservation,
                "note": note,
                "form": form,
                "title": "修改内部备注",
                "submit_label": "保存备注",
            },
        )

    def get(self, request, reservation_pk, note_pk):
        note = self.get_note(reservation_pk, note_pk)
        return self.render_form(
            request,
            note,
            ReservationNoteForm(instance=note),
        )

    def post(self, request, reservation_pk, note_pk):
        note = self.get_note(reservation_pk, note_pk)
        form = ReservationNoteForm(request.POST, instance=note)
        if form.is_valid():
            try:
                _, changed_fields = update_reservation_note(
                    reservation_id=reservation_pk,
                    note_id=note.pk,
                    content=form.cleaned_data["content"],
                    is_important=form.cleaned_data["is_important"],
                    operator=request.user,
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                if changed_fields:
                    messages.success(request, "内部备注已更新。")
                else:
                    messages.info(request, "内部备注没有变化。")
                return redirect("reservation_detail", pk=reservation_pk)
        return self.render_form(request, note, form)


class ReservationNoteDeleteView(StaffRequiredMixin, View):
    template_name = "reservation_note_confirm_delete.html"

    def dispatch(self, request, *args, **kwargs):
        if (
            request.user.is_authenticated
            and request.user.is_staff
            and not can_delete_reservation_note(request.user)
        ):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_note(self, reservation_pk, note_pk):
        return get_object_or_404(
            ReservationNote.objects.select_related("reservation"),
            pk=note_pk,
            reservation_id=reservation_pk,
        )

    def get(self, request, reservation_pk, note_pk):
        note = self.get_note(reservation_pk, note_pk)
        return render(request, self.template_name, {"note": note})

    def post(self, request, reservation_pk, note_pk):
        note = self.get_note(reservation_pk, note_pk)
        delete_reservation_note(
            reservation_id=reservation_pk,
            note_id=note.pk,
            operator=request.user,
        )
        messages.success(request, "内部备注已删除。")
        return redirect("reservation_detail", pk=reservation_pk)


class ReservationListView(
    PreserveQueryStringMixin,
    StaffPermissionRequiredMixin,
    ListView,
):
    model = Reservation
    paginate_by = 10
    context_object_name = "reservations"
    template_name = "reservation_list.html"
    permission_required = "main.view_reservation"

    def get_queryset(self):
        queryset = Reservation.objects.select_related("room", "guest")
        room_number = self.request.GET.get("room_number", "").strip()
        status = self.request.GET.get("status", "").strip()
        if room_number:
            queryset = queryset.filter(room__room_number__iexact=room_number)
        if status in Reservation.Status.values:
            queryset = queryset.filter(status=status)
        return queryset.order_by("-check_in_date", "-id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_status = self.request.GET.get("status", "").strip()
        context["status_choices"] = Reservation.Status.choices
        context["selected_status"] = (
            selected_status if selected_status in Reservation.Status.values else ""
        )
        return context


class ReservationStatusActionView(StaffPermissionRequiredMixin, View):
    permission_required = (
        "main.view_reservation",
        "main.manage_reservation_status",
    )
    transition_function = None
    target_status = None
    action_label = ""

    def get_reservation(self, pk):
        return get_object_or_404(
            Reservation.objects.select_related("room", "guest"), pk=pk
        )

    def get(self, request, pk):
        reservation = self.get_reservation(pk)
        if self.target_status not in get_allowed_transitions(reservation):
            messages.error(
                request,
                f"当前订单状态不允许执行“{self.action_label}”。",
            )
            return redirect("reservation_detail", pk=reservation.pk)
        return render(
            request,
            "reservation_status_confirm.html",
            {
                "reservation": reservation,
                "action_label": self.action_label,
            },
        )

    def post(self, request, pk):
        reservation = self.get_reservation(pk)
        try:
            self.transition_function(
                reservation_id=reservation.pk,
                operator=request.user,
            )
        except ReservationTransitionError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"“{self.action_label}”已完成。")
        return redirect("reservation_detail", pk=reservation.pk)


class ReservationConfirmView(ReservationStatusActionView):
    transition_function = staticmethod(confirm_reservation)
    target_status = Reservation.Status.CONFIRMED
    action_label = "确认订单"


class ReservationCancelView(ReservationStatusActionView):
    transition_function = staticmethod(cancel_reservation)
    target_status = Reservation.Status.CANCELLED
    action_label = "取消订单"


class ReservationCheckInView(ReservationStatusActionView):
    transition_function = staticmethod(check_in_reservation)
    target_status = Reservation.Status.CHECKED_IN
    action_label = "办理入住"


class ReservationCheckOutView(ReservationStatusActionView):
    transition_function = staticmethod(check_out_reservation)
    target_status = Reservation.Status.CHECKED_OUT
    action_label = "办理退房"


class ReservationNoShowView(ReservationStatusActionView):
    transition_function = staticmethod(mark_reservation_no_show)
    target_status = Reservation.Status.NO_SHOW
    action_label = "标记未到店"


class AdminOperationLogListView(
    PreserveQueryStringMixin,
    StaffPermissionRequiredMixin,
    ListView,
):
    model = AdminOperationLog
    template_name = "operation_log_list.html"
    context_object_name = "operation_logs"
    paginate_by = 30
    permission_required = "main.view_adminoperationlog"

    def get_queryset(self):
        return AdminOperationLog.objects.select_related("operator").order_by(
            "-created_at", "-id"
        )
