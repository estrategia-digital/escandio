"""Vista de despacho/entrega de la API movil v2."""
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from movil.serializers.despacho import DespachoMovilSerializer
from movil.views.base import MovilApiMixin
from vertical.models.entrega import VerEntrega


class DespachoMovilView(MovilApiMixin, generics.RetrieveAPIView):
    """Resuelve un codigo de despacho a su resumen + tenant (schema_name).

    Es el endpoint de arranque: corre en el dominio base (no en un subdominio
    de tenant) porque la app todavia no sabe a que tenant pertenece el codigo.
    Por eso basta IsAuthenticated, no EsConductorMovil.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DespachoMovilSerializer
    queryset = VerEntrega.objects.all()

    def get_queryset(self):
        # Admin/coordinador ve todo el contenedor; conductor solo lo asignado a el
        # o aun sin asignar. Fuera de scope -> 404.
        user = self.request.user
        if user.is_superuser:
            return VerEntrega.objects.all()
        from contenedor.models import Contenedor, UsuarioContenedor
        ids_acceso_total = set(Contenedor.objects.filter(
            usuario_id=user.id,
        ).values_list('id', flat=True))
        ids_conductor = set()
        membresias = UsuarioContenedor.objects.filter(
            usuario_id=user.id, tiene_acceso_movil=True,
        ).values_list('contenedor_id', 'perfil_movil')
        for contenedor_id, perfil_movil in membresias:
            if perfil_movil == 'conductor':
                ids_conductor.add(contenedor_id)
            else:
                # coordinador (o sin perfil definido) ve todo el contenedor.
                ids_acceso_total.add(contenedor_id)
        # Ser admin/coordinador de un contenedor manda sobre el rol conductor.
        ids_conductor -= ids_acceso_total
        return VerEntrega.objects.filter(
            Q(contenedor_id__in=ids_acceso_total)
            | (
                Q(contenedor_id__in=ids_conductor)
                & (Q(usuario_id=user.id) | Q(usuario_id__isnull=True))
            )
        )

    @extend_schema(tags=['despachos'])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class DespachosMiasView(MovilApiMixin, generics.ListAPIView):
    """Lista los despachos asignados al conductor autenticado. Sin paginar
    (un conductor maneja pocos despachos vigentes a la vez).

    `?estado=`:
      - `activas` (default): los que aun trabaja (ni finalizados por el conductor
        ni terminados por la oficina).
      - `historial`: los que ya cerro (finalizados por el conductor o terminados).
      - `todas`: sin filtrar por estado.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DespachoMovilSerializer
    pagination_class = None

    def get_queryset(self):
        qs = VerEntrega.objects.filter(
            usuario_id=self.request.user.id,
        ).order_by('-fecha', '-id')
        estado = self.request.query_params.get('estado', 'activas')
        if estado == 'historial':
            qs = qs.filter(Q(estado_finalizado_conductor=True) | Q(estado_terminado=True))
        elif estado != 'todas':
            qs = qs.filter(estado_finalizado_conductor=False, estado_terminado=False)
        return qs

    @extend_schema(
        tags=['despachos'],
        parameters=[OpenApiParameter(
            name='estado', type=str, required=False,
            enum=['activas', 'historial', 'todas'],
            description="Filtra por estado del viaje (default 'activas').",
        )],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class TomarDespachoRequestSerializer(serializers.Serializer):
    """Body de POST /despachos/tomar/: el OE (el numero de Trafico)."""
    oe = serializers.IntegerField(
        min_value=1,
        help_text='El O_E de Trafico (RutDespacho.entrega_id) que el conductor teclea.',
    )


class TomarDespachoView(MovilApiMixin, APIView):
    """El conductor TOMA una orden por su OE (self-service): auto-asignarse.
    Busca el RutDespacho por `entrega_id == oe` en el/los schema(s) del contenedor,
    setea `conductor_id` y propaga `usuario_id` a la VerEntrega PUBLICA para que
    la orden aparezca en "Mis Ordenes" en todos los dispositivos del conductor.

    OJO tenant/public: `RutDespacho` es tenant-only (DENTRO del schema_context).
    `VerEntrega` existe en public Y en cada tenant; el movil lee la de PUBLIC,
    asi que su update va FUERA del schema_context.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['despachos'],
        request=TomarDespachoRequestSerializer,
        responses=DespachoMovilSerializer,
        examples=[OpenApiExample('Tomar por OE', value={'oe': 1234})],
    )
    def post(self, request, *args, **kwargs):
        from django_tenants.utils import schema_context
        from contenedor.models import Contenedor, UsuarioContenedor
        from ruteo.models.despacho import RutDespacho
        from ruteo.models.despacho_evento import RutDespachoEvento
        from ruteo.servicios.evento import registrar_evento

        entrada = TomarDespachoRequestSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        oe = entrada.validated_data['oe']

        contenedor_ids = list(
            UsuarioContenedor.objects.filter(
                usuario_id=request.user.id, tiene_acceso_movil=True,
            ).values_list('contenedor_id', flat=True)
        )
        schemas = list(
            Contenedor.objects.filter(id__in=contenedor_ids)
            .values_list('schema_name', flat=True)
        )

        encontrado = None  # (schema_name, despacho_id)
        for schema_name in schemas:
            with schema_context(schema_name):
                despacho = (
                    RutDespacho.objects
                    .filter(entrega_id=oe, estado_anulado=False)
                    .first()
                )
                if despacho is None:
                    continue
                despacho.conductor_id = request.user.id
                campos = ['conductor_id']
                if not despacho.cargado_por_id:
                    despacho.cargado_por_id = request.user.id
                    despacho.cargado_en = timezone.now()
                    campos += ['cargado_por_id', 'cargado_en']
                despacho.save(update_fields=campos)
                registrar_evento(despacho.id, RutDespachoEvento.TIPO_TOMADO, request.user.id)
                encontrado = (schema_name, despacho.id)
                break

        if encontrado is None:
            return Response(
                {'codigo': 1, 'titulo': 'No encontrada',
                 'mensaje': f'No hay una orden con OE {oe} en tus contenedores.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        schema_name, despacho_id = encontrado
        ve = VerEntrega.objects.filter(
            despacho_id=despacho_id, schema_name=schema_name,
        ).first()
        if ve is None:
            return Response(
                {'codigo': 2, 'titulo': 'Aun no publicada',
                 'mensaje': 'La orden existe pero todavia no esta publicada al '
                            'movil. Proba de nuevo en unos minutos.'},
                status=status.HTTP_409_CONFLICT,
            )
        if ve.usuario_id != request.user.id:
            ve.usuario_id = request.user.id
            ve.save(update_fields=['usuario_id'])
        return Response(DespachoMovilSerializer(ve).data, status=status.HTTP_200_OK)


class SoltarDespachoRequestSerializer(serializers.Serializer):
    """Body de POST /despachos/soltar/: el id (VerEntrega) de la orden a soltar."""
    id = serializers.IntegerField(
        min_value=1,
        help_text='El id de la orden (VerEntrega.id) que el conductor quiere soltar.',
    )


class SoltarDespachoView(MovilApiMixin, APIView):
    """El conductor SUELTA una orden de su "Mis Ordenes" (inverso de tomar).

    Limpia `usuario_id` de SU VerEntrega (public) y, best-effort, el `conductor_id`
    del RutDespacho (tenant). Scopeado por `usuario_id`: solo puede soltar lo que
    tiene asignado.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['despachos'],
        request=SoltarDespachoRequestSerializer,
        responses={200: OpenApiResponse(description='Orden soltada')},
        examples=[OpenApiExample('Soltar orden', value={'id': 14163})],
    )
    def post(self, request, *args, **kwargs):
        entrada = SoltarDespachoRequestSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        ve_id = entrada.validated_data['id']

        ve = VerEntrega.objects.filter(
            pk=ve_id, usuario_id=request.user.id,
        ).first()
        if ve is None:
            return Response(
                {'codigo': 1, 'titulo': 'No encontrada',
                 'mensaje': 'Esa orden no esta asignada a vos.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        schema_name = ve.schema_name
        despacho_id = ve.despacho_id
        ve.usuario_id = None
        ve.save(update_fields=['usuario_id'])
        # Best-effort y fail-silent: la orden ya se solto de Mis Ordenes aunque el
        # despacho sea huerfano/inexistente en el tenant.
        if schema_name and despacho_id:
            from django_tenants.utils import schema_context
            from ruteo.models.despacho import RutDespacho
            from ruteo.models.despacho_evento import RutDespachoEvento
            from ruteo.servicios.evento import registrar_evento
            try:
                with schema_context(schema_name):
                    n = RutDespacho.objects.filter(
                        pk=despacho_id, conductor_id=request.user.id,
                    ).update(conductor_id=None)
                    if n:
                        registrar_evento(despacho_id, RutDespachoEvento.TIPO_SOLTADO, request.user.id)
            except Exception:
                pass
        return Response({'mensaje': 'Soltaste la orden'}, status=status.HTTP_200_OK)


class DespachoIdRequestSerializer(serializers.Serializer):
    """Body de finalizar/reabrir: el id (VerEntrega) de la orden."""
    id = serializers.IntegerField(
        min_value=1,
        help_text='El id de la orden (VerEntrega.id).',
    )


def _mi_ver_entrega(request, ve_id):
    """VerEntrega del usuario (scopeada por usuario_id). None si no es suya."""
    return VerEntrega.objects.filter(pk=ve_id, usuario_id=request.user.id).first()


class FinalizarDespachoView(MovilApiMixin, APIView):
    """El CONDUCTOR finaliza su despacho cuando NO le quedan pendientes (toda guia
    entregada o con novedad). Marca `estado_finalizado_conductor` en el RutDespacho
    (tenant) y en la VerEntrega (public). Es REVERSIBLE (reabrir) y NO crea
    RutTerminacion (eso es del admin).

    Reusa `DespachoServicio.validar_terminacion` (misma regla de "0 pendientes"
    que el Terminar del admin). RutDespacho se lee/escribe DENTRO del
    schema_context; la VerEntrega de public se actualiza FUERA.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['despachos'],
        request=DespachoIdRequestSerializer,
        responses={200: OpenApiResponse(description='Despacho finalizado')},
        examples=[OpenApiExample('Finalizar', value={'id': 14163})],
    )
    def post(self, request, *args, **kwargs):
        entrada = DespachoIdRequestSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        ve = _mi_ver_entrega(request, entrada.validated_data['id'])
        if ve is None:
            return Response(
                {'codigo': 1, 'titulo': 'No encontrada',
                 'mensaje': 'Esa orden no esta asignada a vos.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not (ve.schema_name and ve.despacho_id):
            return Response(
                {'codigo': 2, 'titulo': 'Orden sin despacho',
                 'mensaje': 'Esta orden no tiene un despacho para finalizar.'},
                status=status.HTTP_409_CONFLICT,
            )
        from django_tenants.utils import schema_context
        from ruteo.models.despacho import RutDespacho
        from ruteo.models.despacho_evento import RutDespachoEvento
        from ruteo.servicios.despacho import DespachoServicio
        from ruteo.servicios.evento import registrar_evento
        with schema_context(ve.schema_name):
            despacho = RutDespacho.objects.filter(pk=ve.despacho_id).first()
            if despacho is None:
                return Response(
                    {'codigo': 3, 'titulo': 'No encontrada',
                     'mensaje': 'El despacho ya no existe.'},
                    status=status.HTTP_404_NOT_FOUND,
                )
            ok, mensaje = DespachoServicio.validar_terminacion(despacho)
            if not ok:
                # Codigo 14 = validacion de negocio (mismo que usa el back en 400s).
                return Response(
                    {'codigo': 14, 'titulo': 'Aun tienes pendientes', 'mensaje': mensaje},
                    status=status.HTTP_409_CONFLICT,
                )
            if not despacho.estado_finalizado_conductor:
                despacho.estado_finalizado_conductor = True
                despacho.save(update_fields=['estado_finalizado_conductor'])
                registrar_evento(despacho.id, RutDespachoEvento.TIPO_FINALIZADO, request.user.id)
        if not ve.estado_finalizado_conductor:
            ve.estado_finalizado_conductor = True
            ve.save(update_fields=['estado_finalizado_conductor'])
        return Response({'mensaje': 'Despacho finalizado'}, status=status.HTTP_200_OK)


class ReabrirDespachoView(MovilApiMixin, APIView):
    """El conductor REABRE un despacho que habia finalizado (vuelve de Historial a
    activas), p.ej. porque soluciono una novedad y va a entregar. Revierte
    `estado_finalizado_conductor` (tenant + public). NO se puede reabrir si el
    admin ya lo TERMINO (definitivo): en ese caso queda en Historial.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['despachos'],
        request=DespachoIdRequestSerializer,
        responses={200: OpenApiResponse(description='Despacho reabierto')},
        examples=[OpenApiExample('Reabrir', value={'id': 14163})],
    )
    def post(self, request, *args, **kwargs):
        entrada = DespachoIdRequestSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        ve = _mi_ver_entrega(request, entrada.validated_data['id'])
        if ve is None:
            return Response(
                {'codigo': 1, 'titulo': 'No encontrada',
                 'mensaje': 'Esa orden no esta asignada a vos.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if ve.estado_terminado:
            return Response(
                {'codigo': 4, 'titulo': 'Ya terminado',
                 'mensaje': 'El despacho ya fue terminado por la oficina; no se puede reabrir.'},
                status=status.HTTP_409_CONFLICT,
            )
        if ve.schema_name and ve.despacho_id:
            from django_tenants.utils import schema_context
            from ruteo.models.despacho import RutDespacho
            from ruteo.models.despacho_evento import RutDespachoEvento
            from ruteo.servicios.evento import registrar_evento
            try:
                with schema_context(ve.schema_name):
                    n = RutDespacho.objects.filter(
                        pk=ve.despacho_id, estado_terminado=False,
                    ).update(estado_finalizado_conductor=False)
                    if n:
                        registrar_evento(ve.despacho_id, RutDespachoEvento.TIPO_REABIERTO, request.user.id)
            except Exception:
                pass
        if ve.estado_finalizado_conductor:
            ve.estado_finalizado_conductor = False
            ve.save(update_fields=['estado_finalizado_conductor'])
        return Response({'mensaje': 'Despacho reabierto'}, status=status.HTTP_200_OK)
