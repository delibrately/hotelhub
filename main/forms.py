from django import forms

from .models import Reservation


class ReservationForm(forms.ModelForm):
    """Shared reservation form for management views and Django Admin.

    Date ordering and room availability are centralized in
    ``Reservation.clean()``. Django's ModelForm validation calls that method,
    so every entry point receives the same field-level errors.
    """

    class Meta:
        model = Reservation
        fields = [
            "room",
            "guest",
            "additional",
            "check_in_date",
            "check_out_date",
        ]
        widgets = {
            "check_in_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
            "check_out_date": forms.DateInput(
                attrs={"type": "date"}, format="%Y-%m-%d"
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["check_in_date"].input_formats = ["%Y-%m-%d"]
        self.fields["check_out_date"].input_formats = ["%Y-%m-%d"]
