from django.urls import path
from . import views
from . import retreat

urlpatterns = [
    path('stay/', retreat.retreat_home, name='retreat_home'),
    path('stay/rooms/<slug:slug>/', retreat.retreat_room, name='retreat_room'),
    path('modd', views.ModdView.as_view(), name="modd"),
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('reservations/', views.ReservationListView.as_view(), name='reservation_list'),
    path('reservation/create/', views.ReservationCreateView.as_view(), name='reservation_create'),
    path('reservation/<int:pk>/update', views.ReservationUpdateView.as_view(), name='reservation_update'),
    path('reservation/<int:pk>', views.ReservationDetailView.as_view(), name='reservation_detail'),
    path(
        'reservation/<int:reservation_pk>/notes/add/',
        views.ReservationNoteCreateView.as_view(),
        name='reservation_note_create',
    ),
    path(
        'reservation/<int:reservation_pk>/notes/<int:note_pk>/edit/',
        views.ReservationNoteUpdateView.as_view(),
        name='reservation_note_update',
    ),
    path(
        'reservation/<int:reservation_pk>/notes/<int:note_pk>/delete/',
        views.ReservationNoteDeleteView.as_view(),
        name='reservation_note_delete',
    ),
    path(
        'reservation/<int:pk>/confirm/',
        views.ReservationConfirmView.as_view(),
        name='reservation_confirm',
    ),
    path(
        'reservation/<int:pk>/cancel/',
        views.ReservationCancelView.as_view(),
        name='reservation_cancel',
    ),
    path(
        'reservation/<int:pk>/check-in/',
        views.ReservationCheckInView.as_view(),
        name='reservation_check_in',
    ),
    path(
        'reservation/<int:pk>/check-out/',
        views.ReservationCheckOutView.as_view(),
        name='reservation_check_out',
    ),
    path(
        'reservation/<int:pk>/no-show/',
        views.ReservationNoShowView.as_view(),
        name='reservation_no_show',
    ),
    path(
        'operation-logs/',
        views.AdminOperationLogListView.as_view(),
        name='operation_log_list',
    ),
]
