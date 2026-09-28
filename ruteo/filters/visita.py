import django_filters
from django.db.models import Q, TextField
from django.db.models.functions import Cast
from ruteo.models.visita import RutVisita

class NumberInFilter(django_filters.BaseInFilter, django_filters.NumberFilter):
    pass

class VisitaFilter(django_filters.FilterSet):
    franja_id__in = NumberInFilter(field_name='franja_id', lookup_expr='in')
    despacho__vehiculo__placa = django_filters.CharFilter(field_name='despacho__vehiculo__placa', lookup_expr='icontains')
    # Buscador rapido: un solo campo de texto en vez del armador campo+operador+
    # valor. numero es IntegerField, asi que se castea a texto para permitir la
    # busqueda parcial ("12170" encuentra 1217078); ademas destinatario /
    # documento / placa por icontains. Todo en OR.
    buscar = django_filters.CharFilter(method='filtrar_buscar', label='Busqueda rapida')

    def filtrar_buscar(self, queryset, name, value):
        v = (value or '').strip()
        if not v:
            return queryset
        queryset = queryset.annotate(_numero_txt=Cast('numero', TextField()))
        q = (Q(_numero_txt__icontains=v)
             | Q(destinatario__icontains=v)
             | Q(documento__icontains=v)
             | Q(despacho__vehiculo__placa__icontains=v))
        return queryset.filter(q)

    class Meta:
        model = RutVisita
        fields = {'id': ['exact'],
                  'despacho_id' : ['exact'],
                  'numero': ['exact'],
                  'documento': ['exact', 'icontains'],
                  'estado_entregado': ['exact'],
                  'estado_novedad': ['exact'],
                  'estado_despacho': ['exact'],
                  'estado_decodificado': ['exact'],
                  'estado_decodificado_alerta': ['exact'],
                  'fecha': ['gte', 'lte', 'gt', 'lt', 'exact'],
                  'fecha_entrega': ['gte', 'lte', 'gt', 'lt', 'exact'],
                  'destinatario':['icontains'],
                  'franja_id': ['exact'],
                  'cita_inicio': ['isnull', 'gte', 'lte'],
                  'cita_fin': ['isnull', 'gte', 'lte'],
                  }