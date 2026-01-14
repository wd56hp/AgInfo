"""
URL configuration for aginfo_django project.
"""
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
]

# Customize admin site headers
admin.site.site_header = 'AgInfo Administration'
admin.site.site_title = 'AgInfo Admin'
admin.site.index_title = 'Welcome to AgInfo Administration'

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

