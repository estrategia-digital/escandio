from django.db import models
from ruteo.models.despacho import RutDespacho


class RutDespachoEvento(models.Model):
    TIPO_APROBADO = 'aprobado'
    TIPO_ANULADO = 'anulado'
    TIPO_ASIGNADO = 'asignado'
    TIPO_TOMADO = 'tomado'
    TIPO_SOLTADO = 'soltado'
    TIPO_FINALIZADO = 'finalizado'
    TIPO_REABIERTO = 'reabierto'
    TIPO_TERMINADO = 'terminado'
    TIPO_CHOICES = [
        (TIPO_APROBADO, 'Aprobado'),
        (TIPO_ANULADO, 'Anulado'),
        (TIPO_ASIGNADO, 'Conductor asignado'),
        (TIPO_TOMADO, 'Tomado por OE'),
        (TIPO_SOLTADO, 'Soltado'),
        (TIPO_FINALIZADO, 'Finalizado por el conductor'),
        (TIPO_REABIERTO, 'Reabierto por el conductor'),
        (TIPO_TERMINADO, 'Terminado'),
    ]

    despacho = models.ForeignKey(
        RutDespacho, on_delete=models.CASCADE, related_name='eventos')
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, db_index=True)
    usuario_id = models.IntegerField(null=True)
    fecha = models.DateTimeField(auto_now_add=True)
    detalle = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "rut_despacho_evento"
        ordering = ["-id"]
