from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("invoices/new/", views.new_invoice, name="new_invoice"),
    path("invoices/<int:pk>/", views.invoice, name="invoice"),
    path("invoices/<int:pk>/payment/", views.payment, name="payment"),
    path("sales.csv", views.export_csv, name="export_csv"),
]
