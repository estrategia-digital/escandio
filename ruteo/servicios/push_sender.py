import json
import logging

from django.conf import settings

from ruteo.models.push_token import RutPushToken

logger = logging.getLogger(__name__)


def enviar_push_a_usuarios(usuario_ids, titulo, cuerpo, data=None):
    """Push (web + iOS) a los tokens activos de esos usuarios. Best-effort: cada
    fallo se aísla y sin keys configuradas es no-op."""
    if not usuario_ids:
        return
    tokens = RutPushToken.objects.filter(usuario_id__in=usuario_ids, activo=True)
    for t in tokens:
        try:
            if t.plataforma == RutPushToken.PLATAFORMA_WEB:
                _web_push(t, titulo, cuerpo, data)
            elif t.plataforma == RutPushToken.PLATAFORMA_IOS:
                _apns_push(t, titulo, cuerpo, data)
        except Exception:
            logger.exception('push: fallo enviando al token %s', t.id)


def _web_push(token, titulo, cuerpo, data):
    if not settings.VAPID_PRIVATE_KEY:
        return
    from pywebpush import WebPushException, webpush
    try:
        webpush(
            subscription_info=json.loads(token.token),
            data=json.dumps({'titulo': titulo, 'cuerpo': cuerpo, 'data': data or {}}),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={'sub': settings.VAPID_CLAIMS_EMAIL},
        )
    except WebPushException as e:
        resp = getattr(e, 'response', None)
        if resp is not None and resp.status_code in (404, 410):
            token.activo = False
            token.save(update_fields=['activo'])
        else:
            raise


def _apns_push(token, titulo, cuerpo, data):
    if not (settings.APNS_KEY_PATH and settings.APNS_KEY_ID and settings.APNS_TEAM_ID):
        return
    from aioapns import APNs, NotificationRequest, PushType
    from asgiref.sync import async_to_sync

    async def _send():
        apns = APNs(
            key=settings.APNS_KEY_PATH,
            key_id=settings.APNS_KEY_ID,
            team_id=settings.APNS_TEAM_ID,
            topic=settings.APNS_TOPIC,
            use_sandbox=settings.APNS_USE_SANDBOX,
        )
        await apns.send_notification(NotificationRequest(
            device_token=token.token,
            message={
                'aps': {
                    'alert': {'title': titulo, 'body': cuerpo},
                    'sound': 'default',
                },
                'data': data or {},
            },
            push_type=PushType.ALERT,
        ))

    async_to_sync(_send)()
