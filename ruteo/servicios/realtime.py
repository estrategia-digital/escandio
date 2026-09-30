from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def notificar_seguimiento(schema_name, conductor_id):
    """Avisa por WebSocket (best-effort) a los grupos del conductor y del admin
    del tenant que hubo actividad en el chat. El cliente re-consulta al recibirlo."""
    layer = get_channel_layer()
    if layer is None or not schema_name or not conductor_id:
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
