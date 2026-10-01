from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from ruteo.models.seguimiento import RutSeguimiento
from ruteo.serializers.seguimiento import RutSeguimientoSerializador
from ruteo.filters.seguimiento import SeguimientoFilter
from ruteo.servicios.realtime import notificar_seguimiento
from rest_framework.filters import OrderingFilter
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.exceptions import PermissionDenied
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

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        tenant = getattr(request, 'tenant', None)
        if tenant is not None and not getattr(tenant, 'acceso_seguimiento', False):
            raise PermissionDenied('Conductores en ruta no esta habilitado para este contenedor')

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
        serializer.save(usuario_id=getattr(self.request.user, 'id', None))

    @action(detail=False, methods=['get'], url_path='conductores-en-ruta')
    def conductores_en_ruta(self, request):
        from collections import defaultdict
        from contenedor.models import User
        from ruteo.models.despacho import RutDespacho

        despachos = RutDespacho.objects.filter(
            estado_aprobado=True, estado_terminado=False, estado_anulado=False,
            conductor_id__isnull=False,
        ).values('conductor_id', 'visitas', 'visitas_entregadas', 'conductor_telefono')

        agg = defaultdict(lambda: {'ordenes': 0, 'visitas': 0, 'entregadas': 0, 'telefono': None})
        for d in despachos:
            a = agg[d['conductor_id']]
            a['ordenes'] += 1
            a['visitas'] += int(d['visitas'] or 0)
            a['entregadas'] += int(d['visitas_entregadas'] or 0)
            if not a['telefono'] and d['conductor_telefono']:
                a['telefono'] = d['conductor_telefono']

        resultado = []
        for uid, a in agg.items():
            u = (User.objects.filter(pk=uid)
                 .values('nombre', 'apellido', 'correo', 'username').first()) or {}
            nombre = (f"{u.get('nombre') or ''} {u.get('apellido') or ''}".strip()
                      or u.get('correo') or u.get('username') or f'Usuario {uid}')
            pendiente = RutSeguimiento.objects.filter(
                conductor_id=uid, tipo=RutSeguimiento.TIPO_CONSULTA,
                estado=RutSeguimiento.ESTADO_PENDIENTE,
            ).exists()
            no_leidos = RutSeguimiento.objects.filter(
                conductor_id=uid, es_conductor=True, leido=False,
            ).count()
            ultimo = (RutSeguimiento.objects.filter(conductor_id=uid)
                      .order_by('-fecha_registro')
                      .values('comentario', 'fecha_registro', 'es_conductor').first())
            resultado.append({
                'conductor_id': uid,
                'conductor_nombre': nombre,
                'telefono': a['telefono'],
                'ordenes': a['ordenes'],
                'visitas': a['visitas'],
                'entregadas': a['entregadas'],
                'consulta_pendiente': pendiente,
                'no_leidos': no_leidos,
                'ultimo_mensaje': ultimo,
            })
        resultado.sort(key=lambda r: (not r['consulta_pendiente'], -r['no_leidos']))
        return Response(resultado)

    @action(detail=False, methods=['post'])
    def consultar(self, request):
        conductor_id = request.data.get('conductor_id')
        if not conductor_id:
            return Response(
                {'detail': 'conductor_id es obligatorio.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        ya_pendiente = RutSeguimiento.objects.filter(
            conductor_id=conductor_id,
            tipo=RutSeguimiento.TIPO_CONSULTA,
            estado=RutSeguimiento.ESTADO_PENDIENTE,
        ).exists()
        if ya_pendiente:
            return Response(
                {'detail': 'Ya hay una consulta pendiente para este conductor.'},
                status=status.HTTP_409_CONFLICT,
            )
        opciones = request.data.get('opciones') or [
            'Todo bien', 'Voy retrasado', 'Tengo un problema',
        ]
        consulta = RutSeguimiento.objects.create(
            conductor_id=conductor_id,
            tipo=RutSeguimiento.TIPO_CONSULTA,
            estado=RutSeguimiento.ESTADO_PENDIENTE,
            origen=RutSeguimiento.ORIGEN_MANUAL,
            opciones=opciones,
            comentario=request.data.get('pregunta') or '¿Cómo va el viaje?',
            usuario_id=getattr(request.user, 'id', None),
        )
        notificar_seguimiento(
            request.tenant.schema_name, int(conductor_id),
            titulo='Tráfico', cuerpo='¿Cómo va el viaje?')
        return Response(self.get_serializer(consulta).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'])
    def mensaje(self, request):
        conductor_id = request.data.get('conductor_id')
        texto = (request.data.get('texto') or '').strip()
        if not conductor_id or not texto:
            return Response(
                {'detail': 'conductor_id y texto son obligatorios.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        mensaje = RutSeguimiento.objects.create(
            conductor_id=conductor_id,
            tipo=RutSeguimiento.TIPO_MENSAJE,
            comentario=texto,
            es_conductor=False,
            usuario_id=getattr(request.user, 'id', None),
        )
        notificar_seguimiento(
            request.tenant.schema_name, int(conductor_id),
            titulo='Tráfico', cuerpo=texto)
        return Response(self.get_serializer(mensaje).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='marcar-leidos')
    def marcar_leidos(self, request):
        conductor_id = request.data.get('conductor_id')
        if not conductor_id:
            return Response({'detail': 'conductor_id es obligatorio.'}, status=status.HTTP_400_BAD_REQUEST)
        n = RutSeguimiento.objects.filter(
            conductor_id=conductor_id, es_conductor=True, leido=False,
        ).update(leido=True)
        return Response({'marcados': n})

    @action(detail=False, methods=['get'], url_path='vapid-public-key')
    def vapid_public_key(self, request):
        from django.conf import settings
        return Response({'key': settings.VAPID_PUBLIC_KEY})

    @action(detail=False, methods=['post'], url_path='push-subscription')
    def push_subscription(self, request):
        import json as _json
        from ruteo.models.push_token import RutPushToken
        sub = request.data.get('subscription')
        if not sub:
            return Response({'detail': 'Falta subscription.'}, status=status.HTTP_400_BAD_REQUEST)
        RutPushToken.objects.update_or_create(
            token=_json.dumps(sub),
            defaults={
                'usuario_id': getattr(request.user, 'id', None),
                'plataforma': RutPushToken.PLATAFORMA_WEB,
                'activo': True,
            },
        )
        return Response({'ok': True})
