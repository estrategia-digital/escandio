from django.db import migrations


def habilitar_mindstacklabs(apps, schema_editor):
    Contenedor = apps.get_model('contenedor', 'Contenedor')
    Contenedor.objects.filter(schema_name='mindstacklabs').update(acceso_seguimiento=True)


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0017_contenedor_acceso_seguimiento'),
    ]

    operations = [
        migrations.RunPython(habilitar_mindstacklabs, migrations.RunPython.noop),
    ]
