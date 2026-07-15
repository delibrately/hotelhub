from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.core.exceptions import PermissionDenied


class StaffRequiredMixin(LoginRequiredMixin):
    """Require authentication and an active staff account for business views."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_staff:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class StaffPermissionRequiredMixin(StaffRequiredMixin, PermissionRequiredMixin):
    """Require both staff status and the view's declared Django permission."""


class PreserveQueryStringMixin:
    """Expose GET parameters without ``page`` for pagination links."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query_params = self.request.GET.copy()
        query_params.pop("page", None)
        context["query_string"] = query_params.urlencode()
        return context
