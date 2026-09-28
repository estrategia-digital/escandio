import django_filters
from django.db.models import Q, TextField
from django.db.models.functions import Cast
from ruteo.models.novedad import RutNovedad

class NovedadFilter(django_filters.FilterSet):
    visita__numero = django_filters.NumberFilter(field_name='visita__numero', lookup_expr='exact')
    # Buscador rapido: un solo campo en OR sobre el numero de guia (casteado a
    # texto para busqueda parcial), descripcion / solucion de la novedad, el
    # destinatario y la placa de la visita asociada.
    buscar = django_filters.CharFilter(method='filtrar_buscar', label='Busqueda rapida')

    def filtrar_buscar(self, queryset, name, value):
        v = (value or '').strip()
        if not v:
            return queryset
        queryset = queryset.annotate(_num_txt=Cast('visita__numero', TextField()))
        q = (Q(_num_txt__icontains=v)
             | Q(descripcion__icontains=v)
             | Q(solucion__icontains=v)
             | Q(visita__destinatario__icontains=v)
             | Q(visita__despacho__vehiculo__placa__icontains=v))
        return queryset.filter(q)

    class Meta:
        model = RutNovedad
        fields = {'id': ['exact'],
                  'estado_solucion': ['exact'],
                  'nuevo_complemento': ['exact'],
                  'visita_id': ['exact'],
                  'visita__numero': ['exact'],
                  'fecha': ['gte', 'lte', 'gt', 'lt', 'exact'],
                  }