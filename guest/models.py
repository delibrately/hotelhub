from django.db import models


class Guest(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15)
    government_id = models.CharField(max_length=15)
    address = models.TextField(max_length=200)

    class Meta:
        permissions = [
            (
                "view_guest_sensitive_data",
                "Can view masked guest government identification",
            ),
        ]

    @property
    def masked_government_id(self):
        if not self.government_id:
            return ""
        if len(self.government_id) <= 4:
            return "*" * len(self.government_id)
        return "*" * (len(self.government_id) - 4) + self.government_id[-4:]

    def __str__(self):
        return f"{self.first_name} {self.last_name}".strip()
