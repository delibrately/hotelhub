from django.db import transaction
from django.shortcuts import get_object_or_404, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from accounts.mixins import PreserveQueryStringMixin, StaffPermissionRequiredMixin
from main.models import Reservation
from main.services import log_room_created, log_room_updated

from .models import Room


class RoomCreateView(StaffPermissionRequiredMixin, CreateView):
    model = Room
    template_name = "form.html"
    fields = "__all__"
    success_url = reverse_lazy("room_list")
    permission_required = "room.add_room"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Room"
        return context

    @transaction.atomic
    def form_valid(self, form):
        response = super().form_valid(form)
        log_room_created(operator=self.request.user, room=self.object)
        return response


class RoomListView(
    PreserveQueryStringMixin,
    StaffPermissionRequiredMixin,
    ListView,
):
    model = Room
    context_object_name = "rooms"
    paginate_by = 10
    template_name = "room_list.html"
    permission_required = "room.view_room"

    def get_queryset(self):
        return Room.objects.order_by("room_number", "id")


class RoomDetailView(StaffPermissionRequiredMixin, View):
    permission_required = "room.view_room"

    def get(self, request, pk):
        room = get_object_or_404(Room, pk=pk)
        can_view_reservations = request.user.has_perm("main.view_reservation")
        reservations = None
        if can_view_reservations:
            reservations = (
                room.reservation_set.filter(
                    status__in=Reservation.OCCUPYING_STATUSES,
                    check_out_date__gt=timezone.localdate()
                )
                .select_related("guest")
                .order_by("check_in_date", "id")
            )
        return render(
            request,
            "room_detail.html",
            {
                "room": room,
                "reservations": reservations,
                "can_view_reservations": can_view_reservations,
                "can_view_guests": request.user.has_perm("guest.view_guest"),
            },
        )


class RoomUpdateView(StaffPermissionRequiredMixin, UpdateView):
    model = Room
    template_name = "form.html"
    fields = "__all__"
    permission_required = "room.change_room"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Update Room"
        return context

    def get_success_url(self):
        return reverse("room_detail", kwargs={"pk": self.object.pk})

    @transaction.atomic
    def form_valid(self, form):
        changed_fields = list(form.changed_data)
        response = super().form_valid(form)
        if changed_fields:
            log_room_updated(operator=self.request.user, room=self.object)
        return response
