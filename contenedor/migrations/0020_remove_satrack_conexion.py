from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0019_satrack_conexion'),
    ]

    operations = [
        migrations.DeleteModel(
            name='CtnSatrackConexion',
        ),
    ]
