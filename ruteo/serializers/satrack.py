from rest_framework import serializers

from contenedor.models import CtnSatrackConexion


class CtnSatrackConexionSerializador(serializers.ModelSerializer):
    """Lectura: nunca expone el client_secret ni el access_token cifrados."""
    client_secret = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = CtnSatrackConexion
        fields = [
            'id', 'client_id', 'grant_type', 'estado', 'error_mensaje',
            'token_expira', 'fecha_ultima_consulta',
            'fecha_conexion', 'fecha_actualizacion',
            'client_secret',
        ]
        read_only_fields = [
            'estado', 'error_mensaje', 'token_expira', 'fecha_ultima_consulta',
            'fecha_conexion', 'fecha_actualizacion',
        ]
