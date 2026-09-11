import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import F, Q


def money(paisa):
    return f"{Decimal(paisa) / 100:.2f}"


class Party(models.Model):
    name = models.CharField(max_length=120, unique=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "customers and suppliers"

    def __str__(self):
        return self.name


class Product(models.Model):
    sku = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    unit = models.CharField(max_length=30, default="carton")
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    reorder_level = models.PositiveIntegerField(default=10)
    active = models.BooleanField(default=True)
    stock = models.PositiveIntegerField(default=0, editable=False)
    stock_value = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=Q(selling_price__gt=0), name="positive_selling_price")
        ]

    @property
    def average_cost(self):
        if not self.stock:
            return "0.00"
        return f"{Decimal(self.stock_value) / self.stock / 100:.2f}"

    def __str__(self):
        return f"{self.sku} · {self.name} ({self.stock} {self.unit})"


class Invoice(models.Model):
    SALE = "S"
    PURCHASE = "P"
    KINDS = [(SALE, "Sale"), (PURCHASE, "Purchase")]

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    kind = models.CharField(max_length=1, choices=KINDS)
    party = models.ForeignKey(Party, on_delete=models.PROTECT)
    party_name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    total = models.PositiveBigIntegerField()
    cost = models.PositiveBigIntegerField(default=0)
    paid = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ["-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(paid__lte=F("total")), name="paid_lte_total")
        ]

    @property
    def reference(self):
        return f"{'INV' if self.kind == self.SALE else 'PUR'}-{self.pk:06d}"

    @property
    def total_display(self):
        return money(self.total)

    @property
    def paid_display(self):
        return money(self.paid)

    @property
    def due_display(self):
        return money(self.total - self.paid)

    @property
    def status(self):
        if self.paid == self.total:
            return "Paid"
        return "Part paid" if self.paid else "On credit"

    def __str__(self):
        return self.reference


class Line(models.Model):
    invoice = models.ForeignKey(Invoice, related_name="lines", on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    name = models.CharField(max_length=120)
    unit = models.CharField(max_length=30)
    quantity = models.PositiveIntegerField()
    price = models.PositiveBigIntegerField()
    total = models.PositiveBigIntegerField()
    cost = models.PositiveBigIntegerField()

    @property
    def price_display(self):
        return money(self.price)

    @property
    def total_display(self):
        return money(self.total)


class Receipt(models.Model):
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invoice = models.ForeignKey(Invoice, related_name="receipts", on_delete=models.PROTECT)
    amount = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    @property
    def amount_display(self):
        return money(self.amount)
