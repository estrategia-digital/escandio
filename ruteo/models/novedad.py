from django.db import models
from ruteo.models.visita import RutVisita
from ruteo.models.novedad_tipo import RutNovedadTipo

class RutNovedad(models.Model):
    ORIGEN_APP = 'app'
    ORIGEN_LEGACY = 'legacy'
    ORIGEN_LOGY = 'logy'
    ORIGEN_CHOICES = [
        (ORIGEN_APP, 'App'),
        (ORIGEN_LEGACY, 'App (legacy)'),
        (ORIGEN_LOGY, 'LOGY (WhatsApp)'),
    ]

    fecha = models.DateTimeField()
    fecha_registro = models.DateTimeField(auto_now_add=True, null=True)
    fecha_solucion = models.DateTimeField(null=True)
    descripcion = models.CharField(max_length=255, null=True)
    solucion = models.CharField(max_length=255, null=True)
    estado_solucion = models.BooleanField(default = False)
    nuevo_complemento = models.BooleanField(default = False)
    nuevo_complemento_intentos = models.PositiveIntegerField(default=0)
    movil_token = models.CharField(max_length=50, null=True)
    creado_por_id = models.IntegerField(null=True)
    origen = models.CharField(max_length=20, choices=ORIGEN_CHOICES, null=True)
    solucionado_por_id = models.IntegerField(null=True)
    visita = models.ForeignKey(RutVisita, on_delete=models.CASCADE, related_name='novedades_visita_rel')
    novedad_tipo = models.ForeignKey(RutNovedadTipo, on_delete=models.PROTECT, related_name='novedades_novedad_tipo_rel')        

    class Meta:
        db_table = "rut_novedad"
        ordering = ["-id"]