from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase

from shop.models import Invoice, Party, Product, Receipt
from shop.services import post_invoice, receive_payment


class TransactionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="owner", password="testing-only-password", is_staff=True
        )
        self.party = Party.objects.create(name="Test customer")
        self.product = Product.objects.create(sku="RICE", name="Rice", selling_price="120.00")

    def post(self, kind="P", quantity=10, price="100.00", paid="0", token=None):
        return post_invoice(
            actor=self.user,
            kind=kind,
            party_id=self.party.pk,
            rows=[
                {
                    "product_id": self.product.pk,
                    "quantity": quantity,
                    "price": Decimal(price),
                }
            ],
            paid=Decimal(paid),
            token=token or uuid4(),
        )

    def test_purchase_then_sale_updates_stock_and_profit_cost(self):
        self.post()
        sale = self.post(kind="S", quantity=2, price="120.00", paid="40")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        self.assertEqual(self.product.stock_value, 80000)
        self.assertEqual((sale.total, sale.cost, sale.paid), (24000, 20000, 4000))

    def test_weighted_average_cost(self):
        self.post(quantity=10, price="100")
        self.post(quantity=10, price="120")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 20)
        self.assertEqual(self.product.average_cost, "110.00")

    def test_oversell_rolls_back_everything(self):
        self.post(quantity=2)
        with self.assertRaises(ValueError):
            self.post(kind="S", quantity=3)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 2)
        self.assertEqual(Invoice.objects.count(), 1)

    def test_later_line_failure_rolls_back_earlier_line(self):
        self.post(quantity=2)
        empty = Product.objects.create(sku="EMPTY", name="Empty", selling_price="10")
        with self.assertRaises(ValueError):
            post_invoice(
                actor=self.user,
                kind="S",
                party_id=self.party.pk,
                rows=[
                    {"product_id": self.product.pk, "quantity": 1, "price": Decimal("120")},
                    {"product_id": empty.pk, "quantity": 1, "price": Decimal("10")},
                ],
                paid=Decimal("0"),
                token=uuid4(),
            )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 2)

    def test_duplicate_submit_does_not_duplicate_stock(self):
        token = uuid4()
        first = self.post(token=token)
        second = self.post(token=token)
        self.product.refresh_from_db()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(self.product.stock, 10)

    def test_customer_payment_updates_invoice_once(self):
        self.post()
        sale = self.post(kind="S", quantity=1, price="120", paid="20")
        token = uuid4()
        for _ in range(2):
            receive_payment(actor=self.user, invoice_id=sale.pk, amount=Decimal("100"), token=token)
        sale.refresh_from_db()
        self.assertEqual(sale.status, "Paid")
        self.assertEqual(sale.paid, 12000)
        self.assertEqual(Receipt.objects.count(), 1)

    def test_overpayment_is_rejected(self):
        self.post()
        sale = self.post(kind="S", quantity=1, price="120")
        with self.assertRaises(ValueError):
            receive_payment(
                actor=self.user, invoice_id=sale.pk, amount=Decimal("121"), token=uuid4()
            )
        sale.refresh_from_db()
        self.assertEqual(sale.paid, 0)

    def test_invalid_quantities_and_prices_are_rejected(self):
        for quantity, price in [(0, "100"), (-1, "100"), (1, "-1"), (1, "1.001")]:
            with self.subTest(quantity=quantity, price=price):
                with self.assertRaises(ValueError):
                    self.post(quantity=quantity, price=price)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_non_staff_cannot_post(self):
        self.user.is_staff = False
        with self.assertRaises(PermissionError):
            self.post()
