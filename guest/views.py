from django.db import transaction
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from accounts.mixins import PreserveQueryStringMixin, StaffPermissionRequiredMixin
from main.services import log_guest_created, log_guest_updated

from .models import Guest


class GuestCreateView(StaffPermissionRequiredMixin, CreateView):
    model = Guest
    template_name = "form.html"
    fields = "__all__"
    success_url = reverse_lazy("guest_list")
    permission_required = "guest.add_guest"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Create Guest"
        return context

    @transaction.atomic
    def form_valid(self, form):
        response = super().form_valid(form)
        log_guest_created(operator=self.request.user, guest=self.object)
        return response


class GuestListView(
    PreserveQueryStringMixin,
    StaffPermissionRequiredMixin,
    ListView,
):
    model = Guest
    context_object_name = "guests"
    paginate_by = 10
    template_name = "guest_list.html"
    permission_required = "guest.view_guest"

    def get_queryset(self):
        return Guest.objects.order_by("-id")


class GuestDetailView(StaffPermissionRequiredMixin, DetailView):
    model = Guest
    template_name = "guest_detail.html"
    context_object_name = "guest"
    permission_required = "guest.view_guest"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["can_view_sensitive_data"] = self.request.user.has_perm(
            "guest.view_guest_sensitive_data"
        )
        return context


class GuestUpdateView(StaffPermissionRequiredMixin, UpdateView):
    model = Guest
    template_name = "form.html"
    fields = ["first_name", "last_name", "email", "phone_number", "address"]
    permission_required = "guest.change_guest"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Update Guest"
        return context

    def get_success_url(self):
        return reverse("guest_detail", kwargs={"pk": self.object.pk})

    @transaction.atomic
    def form_valid(self, form):
        changed_fields = list(form.changed_data)
        response = super().form_valid(form)
        if changed_fields:
            log_guest_updated(operator=self.request.user, guest=self.object)
        return response
