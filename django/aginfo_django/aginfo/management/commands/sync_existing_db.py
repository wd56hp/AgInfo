"""
Management command to sync Django with existing database tables.
This command creates Django's internal tables without modifying existing AgInfo tables.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Sync Django with existing database (creates Django internal tables only)'

    def handle(self, *args, **options):
        self.stdout.write('Syncing Django with existing database...')
        self.stdout.write('Note: This will only create Django internal tables, not modify existing AgInfo tables.')
        
        # Run migrations (only creates Django internal tables)
        call_command('migrate', verbosity=1, interactive=False)
        
        self.stdout.write(
            self.style.SUCCESS(
                'Successfully synced. Django is ready to use with existing AgInfo database.'
            )
        )

