"""Registro de respuestas de seguimiento (check-in) v2.

El conductor responde una consulta '¿como va el viaje?' desde la app. La
respuesta nace offline y se sincroniza; es idempotente por `movil_token`
(mismo patron que registrar_novedad).
"""
from django.db import transaction

from ruteo.models.seguimiento import RutSeguimiento


def responder_consulta(consulta, opcion, comentario, movil_token, fecha, usuario_id):
    """Crea la fila 'respuesta' y flipa la consulta a 'respondida'.

    Idempotente por `movil_token`: si ya existe una respuesta con ese token la
    devuelve sin duplicar. `fecha` ya es un datetime aware; `consulta` ya fue
    validada como una consulta pendiente.
    """
    existente = RutSeguimiento.objects.filter(movil_token=movil_token).first()
    if existente:
        return existente

    with transaction.atomic():
        respuesta = RutSeguimiento.objects.create(
            conductor_id=consulta.conductor_id,
            despacho_id=consulta.despacho_id,
            tipo=RutSeguimiento.TIPO_RESPUESTA,
            consulta=consulta,
            opcion=opcion,
            comentario=comentario,
            es_conductor=True,
            usuario_id=usuario_id,
            movil_token=movil_token,
        )
        # fecha_registro es auto_now_add (ignora el valor en create). La respuesta
        # pudo generarse offline horas antes de sincronizar, asi que fijamos la
        # hora sellada por la app con update(), que no dispara auto_now_add.
        RutSeguimiento.objects.filter(pk=respuesta.pk).update(fecha_registro=fecha)
        respuesta.fecha_registro = fecha
        # Flipa la consulta original a respondida (solo si sigue pendiente, para
        # no pisar una expiracion posterior).
        RutSeguimiento.objects.filter(
            pk=consulta.pk, estado=RutSeguimiento.ESTADO_PENDIENTE,
        ).update(estado=RutSeguimiento.ESTADO_RESPONDIDA)
    return respuesta
