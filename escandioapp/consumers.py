import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer


class SeguimientoConsumer(AsyncWebsocketConsumer):
    """Canal en vivo del chat/check-in. Es un relay pub/sub: las escrituras van
    por REST (que persisten y hacen broadcast); este consumer solo entrega.

    Autenticación por query params: ?token=<access JWT>&schema=<tenant>&role=
    conductor|admin. El conductor escucha su hilo; el admin escucha todos los
    hilos del tenant.
    """

    async def connect(self):
        qs = parse_qs(self.scope['query_string'].decode())
        token = (qs.get('token') or [None])[0]
        schema = (qs.get('schema') or [None])[0]
        role = (qs.get('role') or ['conductor'])[0]
        user_id = await self._user_id(token)
        if not user_id or not schema:
            await self.close()
            return
        self.group = (
            f'chat_{schema}_admin' if role == 'admin'
            else f'chat_{schema}_{user_id}'
        )
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        group = getattr(self, 'group', None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def seguimiento_evento(self, event):
        await self.send(text_data=json.dumps(event['payload']))

    @database_sync_to_async
    def _user_id(self, token):
        if not token:
            return None
        try:
            from rest_framework_simplejwt.tokens import AccessToken
            return AccessToken(token)['user_id']
        except Exception:
            return None
