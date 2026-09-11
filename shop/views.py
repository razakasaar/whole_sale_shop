import csv
from functools import wraps
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import OperationalError
from django.db.models import F, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods

from .forms import InvoiceForm, Lines, PaymentForm
from .models import Invoice, Party, Product, money
from .services import post_invoice, receive_payment


def staff(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_active or not request.user.is_staff:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


@staff
@require_GET
def dashboard(request):
    sales = Invoice.objects.filter(kind=Invoice.SALE)
    totals = sales.aggregate(total=Sum("total"), cost=Sum("cost"), paid=Sum("paid"))
    total, cost, paid = (totals[key] or 0 for key in ("total", "cost", "paid"))
    products = Product.objects.filter(active=True)
    query = request.GET.get("q", "").strip()
    if query:
        products = products.filter(name__icontains=query)
    customers = Party.objects.filter(invoice__kind=Invoice.SALE).annotate(
        due=Sum(F("invoice__total") - F("invoice__paid"))
    )
    return render(
        request,
        "shop/dashboard.html",
        {
            "products": products,
            "invoices": Invoice.objects.select_related("party")[:100],
            "customers": [{"name": party.name, "due": money(party.due)} for party in customers],
            "sales": money(total),
            "profit": money(total - cost),
            "cash": money(paid),
            "dues": money(total - paid),
            "query": query,
        },
    )


@staff
@require_http_methods(["GET", "POST"])
def new_invoice(request):
    form = InvoiceForm(request.POST or None, initial={"token": uuid4()})
    lines = Lines(request.POST or None, prefix="lines")
    if request.method == "POST":
        header_valid = form.is_valid()
        lines_valid = lines.is_valid()
        if header_valid and lines_valid:
            rows = [
                {
                    "product_id": line.cleaned_data["product"].pk,
                    "quantity": line.cleaned_data["quantity"],
                    "price": line.cleaned_data["price"],
                }
                for line in lines.forms
                if line.cleaned_data
            ]
            try:
                invoice = post_invoice(
                    actor=request.user,
                    kind=form.cleaned_data["kind"],
                    party_id=form.cleaned_data["party"].pk,
                    rows=rows,
                    paid=form.cleaned_data["paid"],
                    token=form.cleaned_data["token"],
                )
            except (ValueError, ObjectDoesNotExist) as exc:
                form.add_error(None, str(exc))
            except OperationalError:
                form.add_error(None, "Database busy. Try saving again; do not change this form.")
            else:
                messages.success(request, "Invoice saved and inventory updated.")
                return redirect("invoice", pk=invoice.pk)
    return render(request, "shop/new_invoice.html", {"form": form, "lines": lines})


@staff
@require_GET
def invoice(request, pk):
    document = get_object_or_404(Invoice.objects.prefetch_related("lines", "receipts"), pk=pk)
    return render(request, "shop/invoice.html", {"invoice": document})


@staff
@require_http_methods(["GET", "POST"])
def payment(request, pk):
    document = get_object_or_404(Invoice, pk=pk, kind=Invoice.SALE)
    form = PaymentForm(
        request.POST or None,
        initial={"token": uuid4(), "amount": document.due_display},
    )
    if request.method == "POST" and form.is_valid():
        try:
            receive_payment(
                actor=request.user,
                invoice_id=document.pk,
                amount=form.cleaned_data["amount"],
                token=form.cleaned_data["token"],
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        except OperationalError:
            form.add_error(None, "Database busy. Try saving again.")
        else:
            messages.success(request, "Payment saved.")
            return redirect("invoice", pk=document.pk)
    return render(request, "shop/payment.html", {"form": form, "invoice": document})


def csv_text(value):
    value = str(value)
    if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + value
    return value


@staff
@require_GET
def export_csv(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="stockroom-sales.csv"'
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(["Invoice", "Date", "Customer", "Total Rs", "Paid Rs", "Due Rs", "Status"])
    for document in Invoice.objects.filter(kind=Invoice.SALE).iterator():
        writer.writerow(
            [
                document.reference,
                document.created_at.isoformat(),
                csv_text(document.party_name),
                document.total_display,
                document.paid_display,
                document.due_display,
                document.status,
            ]
        )
    return response
