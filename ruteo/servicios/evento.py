from ruteo.models.despacho_evento import RutDespachoEvento


def registrar_evento(despacho_id, tipo, usuario_id=None, detalle=None):
    RutDespachoEvento.objects.create(
        despacho_id=despacho_id,
        tipo=tipo,
        usuario_id=usuario_id,
        detalle=detalle,
    )
