from django.db import migrations


def marcar_recogidas(apps, schema_editor):
    """Backfill: las guías existentes cuyo destinatario contiene "RECOGIDA" se
    marcan tipo='recogida'. Es la única señal histórica disponible (no había
    campo tipo). Corre por-tenant vía migrate_schemas."""
    RutVisita = apps.get_model('ruteo', 'RutVisita')
    RutVisita.objects.filter(destinatario__icontains='RECOGIDA').update(tipo='recogida')


def revertir(apps, schema_editor):
    RutVisita = apps.get_model('ruteo', 'RutVisita')
    RutVisita.objects.filter(destinatario__icontains='RECOGIDA').update(tipo='entrega')


class Migration(migrations.Migration):

    dependencies = [
        ('ruteo', '0023_rutvisita_tipo'),
    ]

    operations = [
        migrations.RunPython(marcar_recogidas, revertir),
    ]
