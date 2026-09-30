from rest_framework import serializers
from ruteo.models.seguimiento import RutSeguimiento
from ruteo.serializers.despacho import _ConductorNombreMixin


class RutSeguimientoSerializador(_ConductorNombreMixin, serializers.ModelSerializer):
    class Meta:
        model = RutSeguimiento
        # movil_token NO se expone (es interno de idempotencia).
        fields = [
            'id', 'fecha_registro', 'comentario', 'despacho', 'usuario_id',
            'conductor_id', 'tipo', 'estado', 'origen', 'opciones', 'opcion',
            'consulta', 'es_conductor', 'leido',
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Nombre del autor del evento (admin o conductor). usuario_id no es FK.
        data['autor_nombre'] = self._nombre_conductor(instance.usuario_id)
        return data
