"""ASGI config for escandioapp: HTTP por Django + WebSocket por Channels."""
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'escandioapp.settings')

from django.core.asgi import get_asgi_application

django_asgi = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path

from escandioapp.consumers import SeguimientoConsumer

application = ProtocolTypeRouter({
    'http': django_asgi,
    'websocket': URLRouter([
        path('ws/seguimiento/', SeguimientoConsumer.as_asgi()),
    ]),
})
