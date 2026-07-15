from django.urls import path
from .views import GuestCreateView, GuestDetailView, GuestListView, GuestUpdateView

urlpatterns = [
    path('guests/create/', GuestCreateView.as_view(), name="guest_create"),
    path('guests/', GuestListView.as_view(), name='guest_list'),
    path('guests/<int:pk>/', GuestDetailView.as_view(), name='guest_detail'),
    path('guests/<int:pk>/update/', GuestUpdateView.as_view(), name='guest_update'),
]
