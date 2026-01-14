"""
GeoDjango models for AgInfo database.
These models match the existing database schema.
"""
from django.contrib.gis.db import models
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError


class Company(models.Model):
    """Company/Organization model"""
    company_id = models.AutoField(primary_key=True, db_column='company_id')
    name = models.CharField(max_length=200, unique=True)
    website_url = models.URLField(max_length=300, blank=True, null=True)
    phone_main = models.CharField(max_length=50, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'company'
        verbose_name = 'Company'
        verbose_name_plural = 'Companies'
        ordering = ['name']

    def __str__(self):
        return self.name


class FacilityType(models.Model):
    """Facility type model"""
    facility_type_id = models.AutoField(primary_key=True, db_column='facility_type_id')
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    is_producer = models.BooleanField(default=False)
    is_consumer = models.BooleanField(default=False)
    is_storage = models.BooleanField(default=False)

    class Meta:
        db_table = 'facility_type'
        verbose_name = 'Facility Type'
        verbose_name_plural = 'Facility Types'
        ordering = ['name']

    def __str__(self):
        return self.name


class Facility(models.Model):
    """Facility model with GeoDjango Point geometry"""
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('PLANNED', 'Planned'),
    ]

    facility_id = models.AutoField(primary_key=True, db_column='facility_id')
    company = models.ForeignKey(
        Company,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='company_id',
        related_name='facilities'
    )
    facility_type = models.ForeignKey(
        FacilityType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column='facility_type_id',
        related_name='facilities'
    )

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)

    # Address fields
    address_line1 = models.CharField(max_length=200, blank=True, null=True)
    address_line2 = models.CharField(max_length=200, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    county = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=2, default='KS')
    postal_code = models.CharField(max_length=20, blank=True, null=True)

    # Location fields
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    geom = models.PointField(srid=4326, blank=True, null=True)

    # Status and dates
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    opened_year = models.SmallIntegerField(blank=True, null=True)
    closed_year = models.SmallIntegerField(blank=True, null=True)

    # Contact information
    website_url = models.URLField(max_length=300, blank=True, null=True)
    phone_main = models.CharField(max_length=50, blank=True, null=True)
    email_main = models.EmailField(max_length=200, blank=True, null=True)

    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'facility'
        verbose_name = 'Facility'
        verbose_name_plural = 'Facilities'
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Auto-generate geometry from lat/lon if not provided"""
        if self.geom is None and self.longitude and self.latitude:
            from django.contrib.gis.geos import Point
            self.geom = Point(float(self.longitude), float(self.latitude), srid=4326)
        super().save(*args, **kwargs)


class FacilityContact(models.Model):
    """Contact person for a facility"""
    contact_id = models.AutoField(primary_key=True, db_column='contact_id')
    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        db_column='facility_id',
        related_name='contacts'
    )
    name = models.CharField(max_length=200)
    role_title = models.CharField(max_length=150, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(max_length=200, blank=True, null=True)
    is_primary = models.BooleanField(default=False)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'facility_contact'
        verbose_name = 'Facility Contact'
        verbose_name_plural = 'Facility Contacts'
        ordering = ['-is_primary', 'name']

    def __str__(self):
        return f"{self.name} ({self.facility.name})"


class ServiceType(models.Model):
    """Service type model"""
    service_type_id = models.AutoField(primary_key=True, db_column='service_type_id')
    name = models.CharField(max_length=150, unique=True)
    category = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'service_type'
        verbose_name = 'Service Type'
        verbose_name_plural = 'Service Types'
        ordering = ['name']

    def __str__(self):
        return self.name


class FacilityService(models.Model):
    """Many-to-many relationship between facilities and services"""
    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        db_column='facility_id',
        related_name='services'
    )
    service_type = models.ForeignKey(
        ServiceType,
        on_delete=models.CASCADE,
        db_column='service_type_id'
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'facility_service'
        unique_together = [['facility', 'service_type']]
        verbose_name = 'Facility Service'
        verbose_name_plural = 'Facility Services'

    def __str__(self):
        return f"{self.facility.name} - {self.service_type.name}"


class Product(models.Model):
    """Product model"""
    product_id = models.AutoField(primary_key=True, db_column='product_id')
    name = models.CharField(max_length=150, unique=True)
    category = models.CharField(max_length=50, blank=True, null=True)
    unit_default = models.CharField(max_length=20, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'product'
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['name']

    def __str__(self):
        return self.name


class FacilityProduct(models.Model):
    """Many-to-many relationship between facilities and products"""
    FLOW_ROLE_CHOICES = [
        ('INBOUND', 'Inbound'),
        ('OUTBOUND', 'Outbound'),
        ('BOTH', 'Both'),
    ]
    USAGE_ROLE_CHOICES = [
        ('CONSUMES', 'Consumes'),
        ('PRODUCES', 'Produces'),
        ('STORES', 'Stores'),
        ('RETAILS', 'Retails'),
        ('HANDLES', 'Handles'),
    ]

    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        db_column='facility_id',
        related_name='products'
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        db_column='product_id'
    )
    flow_role = models.CharField(max_length=20, choices=FLOW_ROLE_CHOICES)
    usage_role = models.CharField(max_length=20, choices=USAGE_ROLE_CHOICES)
    is_bulk = models.BooleanField(default=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'facility_product'
        unique_together = [['facility', 'product', 'flow_role', 'usage_role']]
        verbose_name = 'Facility Product'
        verbose_name_plural = 'Facility Products'

    def __str__(self):
        return f"{self.facility.name} - {self.product.name}"


class TransportMode(models.Model):
    """Transport mode model"""
    transport_mode_id = models.AutoField(primary_key=True, db_column='transport_mode_id')
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        db_table = 'transport_mode'
        verbose_name = 'Transport Mode'
        verbose_name_plural = 'Transport Modes'
        ordering = ['name']

    def __str__(self):
        return self.name


class FacilityTransportMode(models.Model):
    """Many-to-many relationship between facilities and transport modes"""
    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        db_column='facility_id',
        related_name='transport_modes'
    )
    transport_mode = models.ForeignKey(
        TransportMode,
        on_delete=models.CASCADE,
        db_column='transport_mode_id'
    )
    notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'facility_transport_mode'
        unique_together = [['facility', 'transport_mode']]
        verbose_name = 'Facility Transport Mode'
        verbose_name_plural = 'Facility Transport Modes'

    def __str__(self):
        return f"{self.facility.name} - {self.transport_mode.name}"

