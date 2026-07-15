from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy
from django.shortcuts import render
from django.views.generic.edit import UpdateView


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    template_name = 'form.html'
    success_url = reverse_lazy('profile')
    fields = ['first_name', 'last_name', 'email']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Profile Update"
        return context
    
    def get_object(self, queryset=None):
        return self.request.user


class PasswordUpdateView(LoginRequiredMixin, PasswordChangeView):
    form_class = PasswordChangeForm
    template_name = 'form.html'
    success_url = reverse_lazy('index')
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["title"] = "Password change"
        return context


@login_required
def profile_view(request):
    return render(request, 'accounts/profile.html')
