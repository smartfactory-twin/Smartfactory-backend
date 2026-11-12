from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('equipements', '0007_machine_type_equipement'),
    ]

    operations = [
        migrations.AlterField(
            model_name='inspectionvisuelle',
            name='image',
            field=models.FileField(
                blank=True,
                default='',
                upload_to='inspections/images/',
                verbose_name='Image inspectée',
            ),
        ),
        migrations.AddField(
            model_name='inspectionvisuelle',
            name='media_type',
            field=models.CharField(
                choices=[('IMAGE', 'Image'), ('VIDEO', 'Vidéo')],
                default='IMAGE',
                max_length=8,
                verbose_name='Type de média',
            ),
        ),
        migrations.AddField(
            model_name='inspectionvisuelle',
            name='image_annotee',
            field=models.FileField(
                blank=True,
                default='',
                upload_to='inspections/annotated/',
                verbose_name='Image annotée',
            ),
        ),
        migrations.AddField(
            model_name='inspectionvisuelle',
            name='annotations',
            field=models.JSONField(blank=True, default=list, verbose_name='Annotations visuelles'),
        ),
    ]
