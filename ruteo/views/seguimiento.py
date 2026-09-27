from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from ruteo.models.seguimiento import RutSeguimiento
from ruteo.serializers.seguimiento import RutSeguimientoSerializador
from ruteo.filters.seguimiento import SeguimientoFilter
from rest_framework.filters import OrderingFilter
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from contenedor.mixins import RolMixin


class RutSeguimientoViewSet(RolMixin, viewsets.ModelViewSet):
    modulo = 'despacho'
    queryset = RutSeguimiento.objects.all()
    serializer_class = RutSeguimientoSerializador
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = SeguimientoFilter
    serializadores = {
        'trafico' : RutSeguimientoSerializador
    }

    def get_serializer_class(self):
        serializador_parametro = self.request.query_params.get('serializador', None)
        if not serializador_parametro or serializador_parametro not in self.serializadores:
            return RutSeguimientoSerializador
        return self.serializadores[serializador_parametro]

    def get_queryset(self):
        page_size = self.request.query_params.get('page_size')
        if page_size:
            if page_size != '0':
                self.pagination_class = PageNumberPagination
                self.pagination_class.page_size = int(page_size)
        queryset = super().get_queryset()
        serializer_class = self.get_serializer_class()        
        select_related = getattr(serializer_class.Meta, 'select_related_fields', [])
        if select_related:
            queryset = queryset.select_related(*select_related)        
        campos = serializer_class.Meta.fields        
        if campos and campos != '__all__':
            queryset = queryset.only(*campos) 
        return queryset 

    def list(self, request, *args, **kwargs):
            if request.query_params.get('lista_completa', '').lower() == 'true':
                self.pagination_class = None
            return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        # El autor del evento web (llamada/nota) es el despachador autenticado.
        # usuario_id no es FK (patron cross-schema); guardamos el id plano.
        serializer.save(usuario_id=getattr(self.request.user, 'id', None))

    @action(detail=False, methods=['post'])
    def consultar(self, request):
        """Trigger MANUAL desde Trafico: crea una consulta '¿como va el viaje?'
        pendiente para que el conductor la responda en la app.

        Body: {despacho_id, opciones?, pregunta?}. Rechaza si ese despacho ya
        tiene una consulta pendiente (evita spamear al conductor).
        """
        despacho_id = request.data.get('despacho_id')
        if not despacho_id:
            return Response(
                {'detail': 'despacho_id es obligatorio.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ya_pendiente = RutSeguimiento.objects.filter(
            despacho_id=despacho_id,
            tipo=RutSeguimiento.TIPO_CONSULTA,
            estado=RutSeguimiento.ESTADO_PENDIENTE,
        ).exists()
        if ya_pendiente:
            return Response(
                {'detail': 'Ya hay una consulta pendiente para este viaje.'},
                status=status.HTTP_409_CONFLICT,
            )

        opciones = request.data.get('opciones') or [
            'Todo bien', 'Voy retrasado', 'Tengo un problema',
        ]
        consulta = RutSeguimiento.objects.create(
            despacho_id=despacho_id,
            tipo=RutSeguimiento.TIPO_CONSULTA,
            estado=RutSeguimiento.ESTADO_PENDIENTE,
            origen=RutSeguimiento.ORIGEN_MANUAL,
            opciones=opciones,
            comentario=request.data.get('pregunta') or '¿Cómo va el viaje?',
            usuario_id=getattr(request.user, 'id', None),
        )
        serializer = self.get_serializer(consulta)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
