from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction

from .models import Invoice, Line, Party, Product, Receipt


def staff_only(actor):
    if not actor.is_authenticated or not actor.is_active or not actor.is_staff:
        raise PermissionError("Staff access is required.")


def paisa(value):
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Enter a valid amount.") from exc
    if not amount.is_finite() or amount < 0 or amount > 100000000:
        raise ValueError("Amount must be between 0 and 100,000,000.")
    if amount != amount.quantize(Decimal("0.01")):
        raise ValueError("Use at most two decimal places.")
    return int(amount * 100)


@transaction.atomic
def post_invoice(*, actor, kind, party_id, rows, paid, token):
    staff_only(actor)
    existing = Invoice.objects.filter(token=token).first()
    if existing:
        if existing.created_by_id != actor.pk:
            raise ValueError("This submission token is already in use.")
        return existing
    if kind not in (Invoice.SALE, Invoice.PURCHASE):
        raise ValueError("Choose sale or purchase.")
    if not 1 <= len(rows) <= 20:
        raise ValueError("Enter between 1 and 20 invoice lines.")

    party = Party.objects.get(pk=party_id)
    total = 0
    cost = 0
    lines = []
    seen = set()

    for row in rows:
        product_id = int(row["product_id"])
        quantity = row["quantity"]
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise ValueError("Quantities must be whole numbers.")
        if not 1 <= quantity <= 100000:
            raise ValueError("Quantity must be between 1 and 100,000.")
        if product_id in seen:
            raise ValueError("Use one line per product; combine duplicate quantities.")
        seen.add(product_id)

        product = Product.objects.select_for_update().get(pk=product_id, active=True)
        price = paisa(row["price"])
        if price <= 0:
            raise ValueError("Unit price must be positive.")
        line_total = quantity * price

        if kind == Invoice.SALE:
            if quantity > product.stock:
                raise ValueError(f"Only {product.stock} {product.unit} of {product.name} remain.")
            line_cost = int(
                (Decimal(product.stock_value) * quantity / product.stock).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )
            product.stock -= quantity
            product.stock_value -= line_cost
        else:
            line_cost = line_total
            product.stock += quantity
            product.stock_value += line_total

        product.save(update_fields=["stock", "stock_value"])
        total += line_total
        cost += line_cost
        lines.append(
            Line(
                product=product,
                name=product.name,
                unit=product.unit,
                quantity=quantity,
                price=price,
                total=line_total,
                cost=line_cost,
            )
        )

    received = paisa(paid) if kind == Invoice.SALE else total
    if received > total:
        raise ValueError("Payment exceeds the invoice total.")

    invoice = Invoice.objects.create(
        token=token,
        kind=kind,
        party=party,
        party_name=party.name,
        created_by=actor,
        total=total,
        cost=cost,
        paid=received,
    )
    for line in lines:
        line.invoice = invoice
    Line.objects.bulk_create(lines)
    return invoice


@transaction.atomic
def receive_payment(*, actor, invoice_id, amount, token):
    staff_only(actor)
    previous = Receipt.objects.filter(token=token).first()
    if previous:
        if previous.invoice_id != invoice_id or previous.created_by_id != actor.pk:
            raise ValueError("This submission token is already in use.")
        return previous

    invoice = Invoice.objects.select_for_update().get(pk=invoice_id, kind=Invoice.SALE)
    received = paisa(amount)
    if received <= 0 or received > invoice.total - invoice.paid:
        raise ValueError("Payment must be positive and cannot exceed the balance.")
    invoice.paid += received
    invoice.save(update_fields=["paid"])
    return Receipt.objects.create(token=token, invoice=invoice, amount=received, created_by=actor)
