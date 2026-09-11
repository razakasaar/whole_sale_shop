from django import forms
from django.forms import formset_factory

from .models import Invoice, Party, Product


class InvoiceForm(forms.Form):
    kind = forms.ChoiceField(choices=Invoice.KINDS)
    party = forms.ModelChoiceField(queryset=Party.objects.all(), label="Customer or supplier")
    paid = forms.DecimalField(
        label="Amount received now (sales only)",
        min_value=0,
        max_value=100000000,
        decimal_places=2,
        initial=0,
        help_text="Enter 0 for credit. Purchases are recorded as paid in full.",
    )
    token = forms.UUIDField(widget=forms.HiddenInput)


class LineForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.filter(active=True))
    quantity = forms.IntegerField(min_value=1, max_value=100000, initial=1)
    price = forms.DecimalField(
        label="Unit price / purchase cost (Rs)",
        min_value="0.01",
        max_value=100000000,
        decimal_places=2,
    )


Lines = formset_factory(
    LineForm, extra=5, min_num=1, validate_min=True, max_num=20, validate_max=True
)


class PaymentForm(forms.Form):
    amount = forms.DecimalField(min_value="0.01", max_value=100000000, decimal_places=2)
    token = forms.UUIDField(widget=forms.HiddenInput)
