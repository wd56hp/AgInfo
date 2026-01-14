"""
Management command to create Django superuser from environment variables.
This command checks if a superuser exists, and if not, creates one using
DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL, and DJANGO_SUPERUSER_PASSWORD.
"""
import os
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import IntegrityError

User = get_user_model()


class Command(BaseCommand):
    help = 'Create a superuser from environment variables if one does not exist'

    def handle(self, *args, **options):
        # Check if any superuser exists
        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write(
                self.style.WARNING('Superuser already exists. Skipping creation.')
            )
            return

        # Get credentials from environment variables
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

        # Check if required variables are set
        if not username or not password:
            self.stdout.write(
                self.style.WARNING(
                    'DJANGO_SUPERUSER_USERNAME and DJANGO_SUPERUSER_PASSWORD '
                    'must be set to create a superuser. Skipping creation.'
                )
            )
            return

        # Create superuser
        try:
            User.objects.create_superuser(
                username=username,
                email=email,
                password=password
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully created superuser "{username}"'
                )
            )
        except IntegrityError:
            self.stdout.write(
                self.style.WARNING(
                    f'User "{username}" already exists. Skipping creation.'
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f'Error creating superuser: {str(e)}'
                )
            )
