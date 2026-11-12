from django.db import migrations
from django.utils import timezone


def require_initial_admin_profile_update(apps, schema_editor):
    User = apps.get_model('accounts', 'Utilisateur')
    User.objects.filter(email__iexact='admin@smartfactory.com').update(
        must_reset_password=True,
        date_joined=timezone.now(),
    )


class Migration(migrations.Migration):
    dependencies = [('accounts', '0004_photo_profil')]

    operations = [
        migrations.RunPython(require_initial_admin_profile_update, migrations.RunPython.noop),
    ]
