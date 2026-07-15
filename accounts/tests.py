from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AuthenticationPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="account-user", password="test-password"
        )

    def test_login_page_is_available_to_anonymous_users(self):
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)

    def test_profile_requires_login(self):
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_password_change_remains_available_to_non_staff_user(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("password-update"))
        self.assertEqual(response.status_code, 200)
