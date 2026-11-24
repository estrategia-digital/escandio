import logging

from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from contenedor.mixins import RolMixin
from ruteo.servicios.satrack import SatrackUbicacionServicio

logger = logging.getLogger(__name__)


class SatrackHabilitadoMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        tenant = getattr(request, 'tenant', None)
        if tenant is not None and not getattr(tenant, 'acceso_satrack', False):
            raise PermissionDenied('Satrack no esta habilitado para este contenedor')


class SatrackUbicacionViewSet(SatrackHabilitadoMixin, RolMixin, viewsets.ViewSet):
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
