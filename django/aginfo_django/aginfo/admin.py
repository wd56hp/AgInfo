"""
Django admin configuration for AgInfo models
"""
from django.contrib.gis import admin
from django.utils.html import format_html
from .models import (
    Company, FacilityType, Facility, FacilityContact,
    ServiceType, FacilityService, Product, FacilityProduct,
    TransportMode, FacilityTransportMode
)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'website_url', 'phone_main')
    search_fields = ('name', 'website_url', 'phone_main')
    list_filter = ('name',)


@admin.register(FacilityType)
class FacilityTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_producer', 'is_consumer', 'is_storage')
    search_fields = ('name', 'description')
    list_filter = ('is_producer', 'is_consumer', 'is_storage')


@admin.register(Facility)
class FacilityAdmin(admin.GISModelAdmin):
    """Facility admin with map widget for geometry"""
    default_lat = 40.0  # Default latitude (center of US)
    default_lon = -100.0  # Default longitude (center of US)
    default_zoom = 4
    list_display = ('name', 'company', 'facility_type', 'city', 'state', 'status', 'view_location')
    list_filter = ('status', 'facility_type', 'state', 'company')
    search_fields = ('name', 'city', 'address_line1', 'company__name')
    readonly_fields = ('facility_id',)
    fieldsets = (
        ('Basic Information', {
            'fields': ('facility_id', 'name', 'description', 'company', 'facility_type', 'status')
        }),
        ('Address', {
            'fields': ('address_line1', 'address_line2', 'city', 'county', 'state', 'postal_code')
        }),
        ('Location', {
            'fields': ('latitude', 'longitude', 'geom')
        }),
        ('Dates', {
            'fields': ('opened_year', 'closed_year')
        }),
        ('Contact Information', {
            'fields': ('website_url', 'phone_main', 'email_main')
        }),
        ('Additional Information', {
            'fields': ('notes',)
        }),
    )

    def view_location(self, obj):
        """Display a link to view location on map"""
        if obj.latitude and obj.longitude:
            url = f"https://www.google.com/maps?q={obj.latitude},{obj.longitude}"
            return format_html('<a href="{}" target="_blank">View on Map</a>', url)
        return "No coordinates"
    view_location.short_description = "Location"


@admin.register(FacilityContact)
class FacilityContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'facility', 'role_title', 'phone', 'email', 'is_primary')
    list_filter = ('is_primary', 'role_title')
    search_fields = ('name', 'facility__name', 'email', 'phone')
    raw_id_fields = ('facility',)


@admin.register(ServiceType)
class ServiceTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'category')
    search_fields = ('name', 'category', 'description')
    list_filter = ('category',)


class FacilityServiceInline(admin.TabularInline):
    model = FacilityService
    extra = 1


@admin.register(FacilityService)
class FacilityServiceAdmin(admin.ModelAdmin):
    list_display = ('facility', 'service_type', 'is_active')
    list_filter = ('is_active', 'service_type')
    search_fields = ('facility__name', 'service_type__name')
    raw_id_fields = ('facility',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'unit_default')
    search_fields = ('name', 'category', 'description')
    list_filter = ('category',)


@admin.register(FacilityProduct)
class FacilityProductAdmin(admin.ModelAdmin):
    list_display = ('facility', 'product', 'flow_role', 'usage_role', 'is_bulk')
    list_filter = ('flow_role', 'usage_role', 'is_bulk', 'product__category')
    search_fields = ('facility__name', 'product__name')
    raw_id_fields = ('facility', 'product')


@admin.register(TransportMode)
class TransportModeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(FacilityTransportMode)
class FacilityTransportModeAdmin(admin.ModelAdmin):
    list_display = ('facility', 'transport_mode')
    search_fields = ('facility__name', 'transport_mode__name')
    raw_id_fields = ('facility',)

