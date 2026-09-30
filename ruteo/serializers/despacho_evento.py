from rest_framework import serializers
from ruteo.models.despacho_evento import RutDespachoEvento
from ruteo.serializers.visita import _EntregadoPorNombreMixin


class RutDespachoEventoSerializador(_EntregadoPorNombreMixin, serializers.ModelSerializer):
    class Meta:
        model = RutDespachoEvento
        fields = ['id', 'despacho', 'tipo', 'usuario_id', 'fecha', 'detalle']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['tipo_nombre'] = instance.get_tipo_display()
        data['usuario_nombre'] = self._nombre_usuario(instance.usuario_id)
        return data
