from django.db import models
from ruteo.models.despacho import RutDespacho


class RutSeguimiento(models.Model):
    """Timeline de seguimiento de un viaje (despacho).

    Cada fila es un EVENTO discriminado por `tipo`:
      - consulta : el admin (o el cron) le pregunta al conductor "¿como va el
                   viaje?" con `opciones`; nace `estado='pendiente'`. La app la
                   trae en el heartbeat y el conductor responde.
      - respuesta: la respuesta del conductor a una consulta (`consulta` self-FK,
                   `opcion` elegida, `es_conductor=True`); al crearse, flipa la
                   consulta a `estado='respondida'`. Offline-safe e idempotente
                   por `movil_token` (mismo patron que RutNovedad).
      - llamada  : registro de una llamada telefonica hecha por el despachador.
      - nota     : nota libre del despachador.
    `usuario_id` = autor del evento (id plano a contenedor.User, NO FK; mismo
    patron cross-schema que RutDespacho.conductor_id). En consultas automaticas
    del cron queda null.
    """

    TIPO_CONSULTA = 'consulta'
    TIPO_RESPUESTA = 'respuesta'
    TIPO_LLAMADA = 'llamada'
    TIPO_NOTA = 'nota'
    TIPOS = [
        (TIPO_CONSULTA, 'Consulta'),
        (TIPO_RESPUESTA, 'Respuesta'),
        (TIPO_LLAMADA, 'Llamada'),
        (TIPO_NOTA, 'Nota'),
    ]

    ESTADO_PENDIENTE = 'pendiente'
    ESTADO_RESPONDIDA = 'respondida'
    ESTADO_EXPIRADA = 'expirada'
    ESTADOS = [
        (ESTADO_PENDIENTE, 'Pendiente'),
        (ESTADO_RESPONDIDA, 'Respondida'),
        (ESTADO_EXPIRADA, 'Expirada'),
    ]

    ORIGEN_MANUAL = 'manual'
    ORIGEN_AUTOMATICO = 'automatico'
    ORIGENES = [
        (ORIGEN_MANUAL, 'Manual'),
        (ORIGEN_AUTOMATICO, 'Automatico'),
    ]

    fecha_registro = models.DateTimeField(auto_now_add=True)
    usuario_id = models.IntegerField(null=True)
    comentario = models.CharField(max_length=500, null=True)
    despacho = models.ForeignKey(
        RutDespacho, null=True, on_delete=models.PROTECT,
        related_name='seguimientos_despacho_rel',
    )
    # --- Timeline / check-in ---
    tipo = models.CharField(max_length=20, choices=TIPOS, default=TIPO_NOTA)
    estado = models.CharField(max_length=20, choices=ESTADOS, null=True, blank=True)
    origen = models.CharField(max_length=20, choices=ORIGENES, null=True, blank=True)
    # Opciones ofrecidas al conductor (en la fila 'consulta'), p.ej.
    # ["Todo bien", "Voy retrasado", "Tengo un problema"].
    opciones = models.JSONField(null=True, blank=True)
    # Opcion elegida por el conductor (en la fila 'respuesta').
    opcion = models.CharField(max_length=100, null=True, blank=True)
    # La 'respuesta' apunta a su 'consulta'.
    consulta = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.PROTECT,
        related_name='respuestas',
    )
    es_conductor = models.BooleanField(default=False)
    # Idempotencia de la respuesta offline (rol de RutNovedad.movil_token).
    movil_token = models.CharField(max_length=50, null=True, blank=True, db_index=True)

    class Meta:
        db_table = "rut_seguimiento"
