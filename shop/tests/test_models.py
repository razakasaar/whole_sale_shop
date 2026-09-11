from django.db import IntegrityError, transaction
from django.test import TestCase

from shop.models import Product


class ProductTests(TestCase):
    def test_sku_must_be_unique(self):
        Product.objects.create(sku="A", name="Rice", selling_price="100.00")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.create(sku="A", name="Other", selling_price="100.00")

    def test_stock_cannot_be_negative(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Product.objects.create(sku="A", name="Rice", selling_price="100.00", stock=-1)

    def test_average_cost_uses_inventory_value(self):
        product = Product(sku="A", name="Rice", stock=10, stock_value=12345, selling_price="15.00")
        self.assertEqual(product.average_cost, "12.35")
