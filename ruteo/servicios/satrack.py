import logging

from django.db import connection
from django.utils import timezone

from contenedor.models import Contenedor, CtnSatrackConexion
from ruteo.models.vehiculo import RutVehiculo
from utilidades.satrack import SatrackCliente

logger = logging.getLogger(__name__)


class SatrackUbicacionServicio:
    """Refresca la posicion de los vehiculos en ruta desde Satrack (query last).

    Solo consulta las placas de vehiculos con despacho activo y pisa
    RutVehiculo.latitud/longitud. Un TTL evita golpear Satrack si varios la
    miran a la vez.
    """

    TTL_SEGUNDOS = 45

    @staticmethod
    def _contenedor_actual():
        return Contenedor.objects.filter(schema_name=connection.schema_name).first()

    @classmethod
    def conexion_actual(cls):
        contenedor = cls._contenedor_actual()
        if not contenedor:
            return None
        return CtnSatrackConexion.objects.filter(contenedor=contenedor).first()

    @staticmethod
    def vehiculos_en_ruta():
        return RutVehiculo.objects.filter(
            despachos_vehiculo_rel__estado_aprobado=True,
            despachos_vehiculo_rel__estado_terminado=False,
            despachos_vehiculo_rel__estado_anulado=False,
        ).exclude(placa__isnull=True).exclude(placa='').distinct()

    @staticmethod
    def _posicion(vehiculo, evento=None):
        posicion = {
            'placa': vehiculo.placa,
            'vehiculo_id': vehiculo.id,
            'latitud': vehiculo.latitud,
            'longitud': vehiculo.longitud,
        }
        if evento:
            posicion.update({
                'direccion': evento.get('address'),
                'ciudad': evento.get('town'),
                'velocidad': evento.get('speed'),
                'ignicion': evento.get('ignition'),
                'sentido': evento.get('direction'),
                'estado_ubicacion': evento.get('locationStatus'),
                'nivel_bateria': evento.get('batteryLevel'),
                'minutos_mismo_sitio': evento.get('samePlaceMinutes'),
                'fecha_generacion': evento.get('generationDate'),
            })
        return posicion

    @classmethod
    def _posiciones_actuales(cls, vehiculos):
        return [cls._posicion(vehiculo) for vehiculo in vehiculos]

    @classmethod
    def refrescar(cls):
        conexion = cls.conexion_actual()
        if not conexion:
            return {'error': True, 'mensaje': 'No hay conexión Satrack configurada para este contenedor'}

        vehiculos = list(cls.vehiculos_en_ruta())
        if not vehiculos:
            return {'error': False, 'posiciones': []}

        if conexion.fecha_ultima_consulta:
            transcurrido = (timezone.now() - conexion.fecha_ultima_consulta).total_seconds()
            if transcurrido < cls.TTL_SEGUNDOS:
                return {'error': False, 'cache': True, 'posiciones': cls._posiciones_actuales(vehiculos)}

        por_placa = {vehiculo.placa: vehiculo for vehiculo in vehiculos}
        cliente = SatrackCliente(conexion)
        resultado = cliente.ultima_ubicacion(list(por_placa.keys()))

        if resultado['error']:
            conexion.estado = CtnSatrackConexion.ESTADO_ERROR
            conexion.error_mensaje = resultado.get('mensaje')
            conexion.save(update_fields=['estado', 'error_mensaje', 'fecha_actualizacion'])
            return resultado

        posiciones = []
        for evento in resultado['eventos']:
            vehiculo = por_placa.get(evento.get('serviceCode'))
            if not vehiculo:
                continue
            latitud = evento.get('latitude')
            longitud = evento.get('longitude')
            if latitud is None or longitud is None:
                continue
            vehiculo.latitud = latitud
            vehiculo.longitud = longitud
            vehiculo.save(update_fields=['latitud', 'longitud'])
            posiciones.append(cls._posicion(vehiculo, evento))

        conexion.estado = CtnSatrackConexion.ESTADO_ACTIVO
        conexion.error_mensaje = None
        conexion.fecha_ultima_consulta = timezone.now()
        conexion.save(update_fields=['estado', 'error_mensaje', 'fecha_ultima_consulta', 'fecha_actualizacion'])
        return {'error': False, 'posiciones': posiciones}
