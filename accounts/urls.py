from django.urls import path
from . import views
urlpatterns = [
    path("password_update/", views.PasswordUpdateView.as_view(), name='password-update'),
    path("profile/", views.profile_view, name='profile'),
    path("profile/update/", views.ProfileUpdateView.as_view(), name='profile-update'),
]
