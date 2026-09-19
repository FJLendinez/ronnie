from ronnie.contrib.admin import ModelAdmin, register

from .models import Product


@register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ("name", "price")
    search_fields = ("name",)
    list_filter = ("name",)
    ordering = ("-price",)
    list_per_page = 2
