from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('voice', '0002_voiceactionproposal_interaction_mode')]

    operations = [
        migrations.AddField(
            model_name='voiceagentrequest',
            name='premiere_phrase_ms',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
