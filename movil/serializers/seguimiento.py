"""Serializers de seguimiento (check-in) de la API movil v2."""
from rest_framework import serializers

from ruteo.models.seguimiento import RutSeguimiento


class ConsultaPendienteMovilSerializer(serializers.ModelSerializer):
    """Consulta '¿como va el viaje?' que el conductor tiene por responder."""
    pregunta = serializers.CharField(source='comentario')

    class Meta:
        model = RutSeguimiento
        fields = ['id', 'despacho_id', 'pregunta', 'opciones', 'fecha_registro']
        read_only_fields = fields


class ResponderConsultaRequestSerializer(serializers.Serializer):
    """Documenta el cuerpo de POST /seguimiento/<id>/responder/."""
    opcion = serializers.CharField(help_text='Opcion elegida de las ofrecidas.')
    comentario = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    movil_token = serializers.CharField(
        help_text='Clave de idempotencia generada por la app.',
    )
    fecha = serializers.CharField(help_text='Formato: YYYY-MM-DD HH:MM')
