"""Vistas de seguimiento (check-in) de la API movil v2.

El despachador consulta '¿como va el viaje?' desde Trafico; el conductor ve la
consulta en la app (heartbeat / al abrir) y responde. La respuesta es
offline-safe e idempotente por `movil_token` (mismo patron que novedades).
"""
from datetime import datetime

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from movil import responses
from movil.permissions import EsConductorMovil
from movil.serializers.comunes import IdSerializer
from movil.serializers.seguimiento import (
    ConsultaPendienteMovilSerializer,
    ResponderConsultaRequestSerializer,
)
from movil.services.seguimiento import responder_consulta
from movil.views.base import MovilApiMixin
from ruteo.models.seguimiento import RutSeguimiento


class SeguimientoMovilViewSet(MovilApiMixin, viewsets.GenericViewSet):
    """Consultas de seguimiento dirigidas al conductor."""
    permission_classes = [EsConductorMovil]
    serializer_class = ConsultaPendienteMovilSerializer
    queryset = RutSeguimiento.objects.all()

    @extend_schema(
        responses={200: ConsultaPendienteMovilSerializer(many=True)},
        tags=['seguimiento'],
    )
    @action(detail=False, methods=['get'], url_path='pendientes')
    def pendientes(self, request):
        """Consultas pendientes de los despachos que conduce este usuario."""
        consultas = RutSeguimiento.objects.filter(
            tipo=RutSeguimiento.TIPO_CONSULTA,
            estado=RutSeguimiento.ESTADO_PENDIENTE,
            despacho__conductor_id=request.user.id,
        ).order_by('fecha_registro')
        return Response(
            ConsultaPendienteMovilSerializer(consultas, many=True).data,
        )

    @extend_schema(
        request=ResponderConsultaRequestSerializer,
        responses={201: IdSerializer},
        tags=['seguimiento'],
    )
    @action(detail=True, methods=['post'], url_path='responder')
    def responder(self, request, pk=None):
        # pk no numerico en la URL (router regex [^/.]+) -> ValueError en el ORM.
        try:
            pk = int(pk)
        except (TypeError, ValueError):
            return responses.error(
                'La consulta no existe', responses.COD_NO_ENCONTRADO, 404,
                titulo='No encontrada',
            )

        opcion = request.data.get('opcion')
        movil_token = request.data.get('movil_token')
        fecha_texto = request.data.get('fecha')
        if not (opcion and movil_token and fecha_texto):
            return responses.error(
                'Faltan parametros (opcion, movil_token, fecha)',
                responses.COD_PARAMETROS, 400, titulo='Datos invalidos',
            )
        try:
            fecha = timezone.make_aware(
                datetime.strptime(fecha_texto, '%Y-%m-%d %H:%M'),
            )
        except (ValueError, TypeError):
            return responses.error(
                'Formato de fecha invalido. Use YYYY-MM-DD HH:MM',
                responses.COD_PARAMETROS, 400, titulo='Datos invalidos',
            )

        consulta = RutSeguimiento.objects.filter(
            pk=pk, tipo=RutSeguimiento.TIPO_CONSULTA,
            despacho__conductor_id=request.user.id,
        ).first()
        if consulta is None:
            return responses.error(
                'La consulta no existe', responses.COD_NO_ENCONTRADO, 404,
                titulo='No encontrada',
            )

        respuesta = responder_consulta(
            consulta=consulta,
            opcion=opcion,
            comentario=request.data.get('comentario'),
            movil_token=movil_token,
            fecha=fecha,
            usuario_id=request.user.id,
        )
        return Response({'id': respuesta.id}, status=201)
