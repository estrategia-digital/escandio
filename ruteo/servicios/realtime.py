from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def notificar_seguimiento(schema_name, conductor_id, *,
                          autor_es_conductor=False, titulo=None, cuerpo=None):
    """Avisa por WebSocket (best-effort) y por push. El cliente re-consulta al
    recibir el evento WS; el push llega a quien NO originó el mensaje (con la app
    o pestaña cerrada)."""
    if not schema_name or not conductor_id:
        return
    _broadcast_ws(schema_name, conductor_id)
    _push(schema_name, conductor_id, autor_es_conductor, titulo, cuerpo)


def _broadcast_ws(schema_name, conductor_id):
    layer = get_channel_layer()
    if layer is None:
        return
    evento = {
        'type': 'seguimiento.evento',
        'payload': {'evento': 'seguimiento', 'conductor_id': conductor_id},
    }
    for group in (f'chat_{schema_name}_{conductor_id}', f'chat_{schema_name}_admin'):
        try:
            async_to_sync(layer.group_send)(group, evento)
        except Exception:
            pass


def _push(schema_name, conductor_id, autor_es_conductor, titulo, cuerpo):
    try:
        from ruteo.models.push_token import RutPushToken
        from ruteo.servicios.push_sender import enviar_push_a_usuarios
        data = {'evento': 'seguimiento', 'conductor_id': conductor_id}
        if autor_es_conductor:
            admin_ids = list(
                RutPushToken.objects.filter(
                    plataforma=RutPushToken.PLATAFORMA_WEB, activo=True,
                ).values_list('usuario_id', flat=True).distinct()
            )
            enviar_push_a_usuarios(
                admin_ids, titulo or 'Conductor', cuerpo or 'Nuevo mensaje', data)
        else:
            enviar_push_a_usuarios(
                [conductor_id], titulo or 'Tráfico', cuerpo or 'Nuevo mensaje', data)
    except Exception:
        pass
