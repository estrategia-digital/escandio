import logging

from django.db import connection
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from contenedor.mixins import RolMixin
from contenedor.models import Contenedor, CtnSatrackConexion
from mensajeria.servicios.cifrado import CifradoServicio
from ruteo.serializers.satrack import CtnSatrackConexionSerializador
from ruteo.servicios.satrack import SatrackUbicacionServicio
from utilidades.satrack import SatrackCliente

logger = logging.getLogger(__name__)


class SatrackConexionViewSet(RolMixin, viewsets.ModelViewSet):
    """Credenciales Satrack del contenedor actual. Solo admin del contenedor."""

    acciones_admin = ['list', 'retrieve', 'create', 'update', 'partial_update', 'destroy', 'probar']
    serializer_class = CtnSatrackConexionSerializador

    def _contenedor_actual(self):
        return Contenedor.objects.filter(schema_name=connection.schema_name).first()

    def get_queryset(self):
        contenedor = self._contenedor_actual()
        if not contenedor:
            return CtnSatrackConexion.objects.none()
        return CtnSatrackConexion.objects.filter(contenedor=contenedor)

    def list(self, request, *args, **kwargs):
        conexion = self.get_queryset().first()
        if not conexion:
            return Response({'detail': 'No hay conexión configurada'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(conexion).data)

    def create(self, request, *args, **kwargs):
        contenedor = self._contenedor_actual()
        if not contenedor:
            return Response({'detail': 'No se pudo identificar el contenedor'}, status=status.HTTP_400_BAD_REQUEST)

        client_id = (request.data.get('client_id') or '').strip()
        client_secret = (request.data.get('client_secret') or '').strip()
        if not client_id or not client_secret:
            return Response({'detail': 'client_id y client_secret son requeridos'}, status=status.HTTP_400_BAD_REQUEST)

        grant_type = (request.data.get('grant_type') or 'client_credentials').strip()

        conexion, _ = CtnSatrackConexion.objects.update_or_create(
            contenedor=contenedor,
            defaults={
                'client_id': client_id,
                'client_secret_cifrado': CifradoServicio.cifrar(client_secret),
                'grant_type': grant_type,
                'access_token_cifrado': None,
                'token_expira': None,
                'estado': CtnSatrackConexion.ESTADO_PENDIENTE,
                'error_mensaje': None,
            },
        )

        resultado = SatrackCliente(conexion).probar()
        if resultado['error']:
            conexion.estado = CtnSatrackConexion.ESTADO_ERROR
            conexion.error_mensaje = resultado.get('mensaje')
        else:
            conexion.estado = CtnSatrackConexion.ESTADO_ACTIVO
            conexion.error_mensaje = None
        conexion.save(update_fields=['estado', 'error_mensaje', 'fecha_actualizacion'])

        return Response(self.get_serializer(conexion).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def probar(self, request):
        conexion = self.get_queryset().first()
        if not conexion:
            return Response({'detail': 'Sin conexión'}, status=status.HTTP_404_NOT_FOUND)
        resultado = SatrackCliente(conexion).probar()
        if resultado['error']:
            conexion.estado = CtnSatrackConexion.ESTADO_ERROR
            conexion.error_mensaje = resultado.get('mensaje')
            conexion.save(update_fields=['estado', 'error_mensaje', 'fecha_actualizacion'])
            return Response({'ok': False, 'mensaje': resultado.get('mensaje')}, status=status.HTTP_400_BAD_REQUEST)
        conexion.estado = CtnSatrackConexion.ESTADO_ACTIVO
        conexion.error_mensaje = None
        conexion.save(update_fields=['estado', 'error_mensaje', 'fecha_actualizacion'])
        return Response({'ok': True})


class SatrackUbicacionViewSet(RolMixin, viewsets.ViewSet):
    """Ubicacion en vivo de los vehiculos en ruta segun Satrack."""

    modulo = 'despacho'

    def list(self, request, *args, **kwargs):
        resultado = SatrackUbicacionServicio.refrescar()
        if resultado['error']:
            return Response({'mensaje': resultado['mensaje'], 'error': True}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'error': False,
            'cache': resultado.get('cache', False),
            'posiciones': resultado['posiciones'],
        })
