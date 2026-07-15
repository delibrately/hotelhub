from django import forms

from .models import Reservation, ReservationNote


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


class ReservationNoteForm(forms.ModelForm):
    content = forms.CharField(
        max_length=5000,
        strip=True,
        error_messages={
            "required": "备注内容不能为空。",
            "max_length": "备注内容不能超过5000个字符。",
        },
        widget=forms.Textarea(attrs={"rows": 6, "maxlength": 5000}),
    )

    class Meta:
        model = ReservationNote
        fields = ["content", "is_important"]

    def clean_content(self):
        content = self.cleaned_data.get("content", "").strip()
        if not content:
            raise forms.ValidationError("备注内容不能为空。")
        if len(content) > 5000:
            raise forms.ValidationError("备注内容不能超过5000个字符。")
        return content

    def clean_is_important(self):
        raw_value = self.data.get(self.add_prefix("is_important"))
        if raw_value in (None, "", False, 0, "0", "false", "False", "off"):
            return False
        if raw_value in (True, 1, "1", "true", "True", "on"):
            return True
        raise forms.ValidationError("是否重要必须是有效的布尔值。")
