from django.contrib import admin, messages

from .forms import ReservationForm
from .models import AdminOperationLog, Reservation
from .services import (
    ReservationTransitionError,
    cancel_reservation,
    check_in_reservation,
    check_out_reservation,
    confirm_reservation,
    log_reservation_created,
    log_reservation_updated,
    mark_reservation_no_show,
)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    form = ReservationForm
    list_display = (
        "id",
        "room",
        "guest",
        "status",
        "check_in_date",
        "check_out_date",
    )
    list_filter = ("status",)
    list_select_related = ("room", "guest")
    ordering = ("-check_in_date", "-id")
    readonly_fields = ("status",)
    actions = (
        "confirm_selected",
        "cancel_selected",
        "check_in_selected",
        "check_out_selected",
        "mark_no_show_selected",
    )

    def save_model(self, request, obj, form, change):
        changed_fields = list(form.changed_data)
        super().save_model(request, obj, form, change)
        if change:
            log_reservation_updated(
                operator=request.user,
                reservation=obj,
                changed_fields=changed_fields,
            )
        else:
            log_reservation_created(operator=request.user, reservation=obj)

    def _can_manage_status(self, request):
        return (
            request.user.is_staff
            and request.user.has_perm("main.view_reservation")
            and request.user.has_perm("main.manage_reservation_status")
        )

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not self._can_manage_status(request):
            for action_name in self.actions:
                actions.pop(action_name, None)
        return actions

    def _run_transition(self, request, queryset, transition_function, label):
        if not self._can_manage_status(request):
            self.message_user(request, "没有订单状态操作权限。", messages.ERROR)
            return

        success_count = 0
        failure_count = 0
        for reservation_id in queryset.values_list("pk", flat=True):
            try:
                transition_function(
                    reservation_id=reservation_id,
                    operator=request.user,
                )
            except (Reservation.DoesNotExist, ReservationTransitionError):
                failure_count += 1
            else:
                success_count += 1

        level = messages.SUCCESS if failure_count == 0 else messages.WARNING
        self.message_user(
            request,
            f"{label}：成功 {success_count} 条，失败 {failure_count} 条。",
            level,
        )

    @admin.action(description="确认选中的订单")
    def confirm_selected(self, request, queryset):
        self._run_transition(request, queryset, confirm_reservation, "确认订单")

    @admin.action(description="取消选中的订单")
    def cancel_selected(self, request, queryset):
        self._run_transition(request, queryset, cancel_reservation, "取消订单")

    @admin.action(description="为选中的订单办理入住")
    def check_in_selected(self, request, queryset):
        self._run_transition(request, queryset, check_in_reservation, "办理入住")

    @admin.action(description="为选中的订单办理退房")
    def check_out_selected(self, request, queryset):
        self._run_transition(request, queryset, check_out_reservation, "办理退房")

    @admin.action(description="将选中的订单标记为未到店")
    def mark_no_show_selected(self, request, queryset):
        self._run_transition(
            request,
            queryset,
            mark_reservation_no_show,
            "标记未到店",
        )


@admin.register(AdminOperationLog)
class AdminOperationLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "operator",
        "action",
        "target_type",
        "target_id",
        "description",
    )
    list_filter = ("action", "target_type", "created_at")
    ordering = ("-created_at", "-id")
    readonly_fields = (
        "operator",
        "action",
        "target_type",
        "target_id",
        "description",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
