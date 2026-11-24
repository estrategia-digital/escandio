import json
import logging
from datetime import timedelta

import requests
from django.utils import timezone

from mensajeria.servicios.cifrado import CifradoServicio

logger = logging.getLogger(__name__)


class SatrackCliente:
    """Consume la API de eventos de ubicacion de Satrack (Keycloak + GraphQL).

    Recibe una CtnSatrackConexion (client_secret cifrado) y expone la consulta
    de ultima ubicacion por placa. El token se cachea cifrado en la conexion.
    """

    URL_AUTENTICACION = 'https://externalsecurityapi.satrack.com/api/v1/Keycloak/authenticate'
    URL_UBICACION = 'http://locationintegrationapi.satrack.com/api/location'
    TIMEOUT_SEGUNDOS = 15
    MARGEN_EXPIRACION_SEGUNDOS = 120
    CAMPOS = (
        'serviceCode latitude longitude address town state direction '
        'generationDate generationDateEpoch speed odometer ignition '
        'locationStatus batteryLevel samePlaceMinutes'
    )

    def __init__(self, conexion):
        self.conexion = conexion

    def _token_vigente(self):
        if not self.conexion.access_token_cifrado or not self.conexion.token_expira:
            return None
        limite = timezone.now() + timedelta(seconds=self.MARGEN_EXPIRACION_SEGUNDOS)
        if self.conexion.token_expira <= limite:
            return None
        return CifradoServicio.descifrar(self.conexion.access_token_cifrado)

    def autenticar(self):
        datos = {
            'client_id': self.conexion.client_id,
            'client_secret': CifradoServicio.descifrar(self.conexion.client_secret_cifrado),
            'grant_type': self.conexion.grant_type,
        }
        try:
            respuesta = requests.post(self.URL_AUTENTICACION, data=datos, timeout=self.TIMEOUT_SEGUNDOS)
        except requests.RequestException as e:
            logger.error('Satrack autenticar: no se pudo contactar Keycloak conexion=%s: %s', self.conexion.id, e)
            return {'error': True, 'mensaje': f'No se pudo contactar el servicio de autenticación de Satrack: {e}'}

        if respuesta.status_code != 200:
            return {'error': True, 'mensaje': 'Credenciales de Satrack inválidas (client_id, client_secret o grant_type)'}

        try:
            cuerpo = respuesta.json()
        except ValueError:
            return {'error': True, 'mensaje': 'Satrack respondió un contenido que no es JSON al autenticar'}

        token = cuerpo.get('access_token')
        if not token:
            return {'error': True, 'mensaje': 'Satrack no devolvió access_token'}

        expira_en = cuerpo.get('expires_in') or 0
        self.conexion.access_token_cifrado = CifradoServicio.cifrar(token)
        self.conexion.token_expira = timezone.now() + timedelta(seconds=int(expira_en))
        self.conexion.save(update_fields=['access_token_cifrado', 'token_expira', 'fecha_actualizacion'])
        return {'error': False, 'token': token}

    def _token(self, forzar=False):
        if not forzar:
            vigente = self._token_vigente()
            if vigente:
                return {'error': False, 'token': vigente}
        return self.autenticar()

    def probar(self):
        return self.autenticar()

    def ultima_ubicacion(self, placas):
        service_codes = json.dumps(list(placas))
        query = '{ last(serviceCodes: %s) { %s } }' % (service_codes, self.CAMPOS)
        return self._consultar(query, lambda data: data.get('last') or [])

    def _consultar(self, query, extraer, reintento=True):
        token = self._token()
        if token['error']:
            return token

        headers = {'Authorization': f'Bearer {token["token"]}', 'Content-Type': 'application/json'}
        try:
            respuesta = requests.post(
                self.URL_UBICACION, json={'query': query}, headers=headers, timeout=self.TIMEOUT_SEGUNDOS,
            )
        except requests.RequestException as e:
            logger.error('Satrack consulta: no se pudo contactar la API conexion=%s: %s', self.conexion.id, e)
            return {'error': True, 'mensaje': f'No se pudo contactar la API de ubicación de Satrack: {e}'}

        if respuesta.status_code == 401:
            if reintento:
                reautenticado = self.autenticar()
                if reautenticado['error']:
                    return reautenticado
                return self._consultar(query, extraer, reintento=False)
            return {'error': True, 'mensaje': 'El token de Satrack no es válido o ya expiró'}

        if respuesta.status_code == 400:
            return {'error': True, 'mensaje': 'Alguna placa consultada no pertenece a la cuenta Satrack del contenedor'}

        if respuesta.status_code != 200:
            return {'error': True, 'mensaje': f'Satrack respondió HTTP {respuesta.status_code}'}

        try:
            cuerpo = respuesta.json()
        except ValueError:
            return {'error': True, 'mensaje': 'Satrack respondió un contenido que no es JSON'}

        errores = cuerpo.get('errors')
        if errores:
            detalle = errores[0].get('message') if isinstance(errores, list) and errores else 'error desconocido'
            return {'error': True, 'mensaje': f'Satrack devolvió un error en la consulta: {detalle}'}

        datos = cuerpo.get('data') or {}
        return {'error': False, 'eventos': extraer(datos)}
