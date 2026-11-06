from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ruteo', '0029_rutpushtoken'),
    ]

    operations = [
        migrations.AddField(
            model_name='rutterminacion',
            name='re_despachadas',
            field=models.IntegerField(default=0),
        ),
    ]
