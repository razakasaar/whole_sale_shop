from django.contrib import admin

from .models import Party, Product

admin.site.site_header = "Stockroom administration"
admin.site.site_title = "Stockroom"


class NoDeleteAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Party)
class PartyAdmin(NoDeleteAdmin):
    list_display = ["name", "phone"]
    search_fields = ["name", "phone"]


@admin.register(Product)
class ProductAdmin(NoDeleteAdmin):
    list_display = ["sku", "name", "stock", "unit", "average_cost", "selling_price", "active"]
    search_fields = ["sku", "name"]
    list_filter = ["active"]
    readonly_fields = ["stock", "stock_value", "average_cost"]
