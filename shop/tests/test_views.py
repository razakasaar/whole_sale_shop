from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


class AccessTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="owner", password="testing-only-password", is_staff=True
        )

    def test_anonymous_users_cannot_open_shop_or_export(self):
        for name in ["dashboard", "new_invoice", "export_csv"]:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)

    def test_non_staff_user_is_denied(self):
        visitor = get_user_model().objects.create_user(username="visitor")
        self.client.force_login(visitor)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)

    def test_staff_can_open_dashboard(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Stockroom")

    def test_invoice_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        response = client.post(reverse("new_invoice"), {})
        self.assertEqual(response.status_code, 403)

    def test_csv_has_download_headers(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("export_csv"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(b"Invoice", response.content)

    def test_invalid_invoice_creates_nothing(self):
        from shop.models import Invoice

        self.client.force_login(self.owner)
        response = self.client.post(reverse("new_invoice"), {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Invoice.objects.count(), 0)
