from rest_framework import serializers
from ruteo.models.novedad import RutNovedad
from ruteo.serializers.visita import _EntregadoPorNombreMixin

class RutNovedadSerializador(_EntregadoPorNombreMixin, serializers.ModelSerializer):
    novedad_tipo__nombre = serializers.CharField(source='novedad_tipo.nombre', read_only=True, allow_null=True, default=None)
    visita__numero = serializers.IntegerField(source='visita.numero', read_only=True, allow_null=True, default=None)
    # descripcion OPCIONAL: la app manda "" (string vacio) cuando el conductor no
    # escribe nada, y el novedad_tipo ya categoriza la novedad. Sin este override el
    # ModelSerializer hereda blank=False del modelo y rechaza "" con 400 (codigo 14,
    # "Errores de validacion") -> era la causa de que TODAS las novedades sin
    # descripcion fallaran al sincronizar. allow_blank cubre "", allow_null cubre None.
    descripcion = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = RutNovedad
        fields = ['id', 'fecha', 'fecha_solucion', 'fecha_registro', 'descripcion', 'solucion', 'estado_solucion', 'visita', 'visita__numero' ,'novedad_tipo',
                  'novedad_tipo__nombre', 'nuevo_complemento', 'movil_token', 'creado_por_id', 'origen', 'solucionado_por_id']
        read_only_fields = ['creado_por_id', 'origen', 'solucionado_por_id']
        select_related_fields = ['novedad_tipo']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['creado_por_nombre'] = self._nombre_usuario(instance.creado_por_id)
        data['origen_nombre'] = instance.get_origen_display() if instance.origen else None
        data['solucionado_por_nombre'] = self._nombre_usuario(instance.solucionado_por_id)
        return data
    
