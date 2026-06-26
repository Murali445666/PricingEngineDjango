from django.contrib import admin

from products.models import (
    LineOfBusiness,
    Network,
    PayerOrganization,
    Product,
    ProductNetworkConfig,
)


@admin.register(PayerOrganization)
class PayerOrganizationAdmin(admin.ModelAdmin):
    list_display = ('payer_id', 'name', 'payer_type')
    search_fields = ('payer_id', 'name')


@admin.register(LineOfBusiness)
class LineOfBusinessAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'payer', 'lob', 'effective_date', 'termination_date')
    list_filter = ('lob',)
    search_fields = ('name', 'product_code')


@admin.register(Network)
class NetworkAdmin(admin.ModelAdmin):
    list_display = ('name', 'payer', 'network_type', 'network_code', 'legacy_payer_network')
    search_fields = ('name', 'network_code')
    list_filter = ('network_type',)


@admin.register(ProductNetworkConfig)
class ProductNetworkConfigAdmin(admin.ModelAdmin):
    list_display = ('product', 'network', 'claim_type', 'effective_date', 'termination_date')
    list_filter = ('claim_type',)
