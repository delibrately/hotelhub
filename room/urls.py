from django.urls import path
from .views import RoomCreateView, RoomDetailView, RoomListView, RoomUpdateView

urlpatterns = [
    path('rooms/create/', RoomCreateView.as_view(), name="room_create"),
    path('rooms/', RoomListView.as_view(), name='room_list'),
    path('rooms/<int:pk>/', RoomDetailView.as_view(), name='room_detail'),
    path('rooms/<int:pk>/update/', RoomUpdateView.as_view(), name='room_update'),
]
