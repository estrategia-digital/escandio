import json
import logging
from datetime import timedelta

import requests
from decouple import config
from django.utils import timezone

logger = logging.getLogger(__name__)

_TOKEN = {'valor': None, 'expira': None}


class SatrackCliente:
    """Consume la API de eventos de ubicacion de Satrack (Keycloak + GraphQL).

    Las credenciales (una sola cuenta de integracion) salen del entorno:
    SATRACK_CLIENT_ID, SATRACK_CLIENT_SECRET, SATRACK_GRANT_TYPE. El token de
    Keycloak dura ~2h y se cachea en memoria por proceso.
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

    @staticmethod
    def _client_id():
        return config('SATRACK_CLIENT_ID', default='')

    @staticmethod
    def _client_secret():
        return config('SATRACK_CLIENT_SECRET', default='')

    @staticmethod
    def _grant_type():
        return config('SATRACK_GRANT_TYPE', default='client_credentials')

    @classmethod
    def configurado(cls):
        return bool(cls._client_id() and cls._client_secret())

    def _token_vigente(self):
        if not _TOKEN['valor'] or not _TOKEN['expira']:
            return None
        if _TOKEN['expira'] <= timezone.now() + timedelta(seconds=self.MARGEN_EXPIRACION_SEGUNDOS):
            return None
        return _TOKEN['valor']

    def autenticar(self):
        datos = {
            'client_id': self._client_id(),
            'client_secret': self._client_secret(),
            'grant_type': self._grant_type(),
        }
        try:
            respuesta = requests.post(self.URL_AUTENTICACION, data=datos, timeout=self.TIMEOUT_SEGUNDOS)
        except requests.RequestException as e:
            logger.error('Satrack autenticar: no se pudo contactar Keycloak: %s', e)
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
        _TOKEN['valor'] = token
        _TOKEN['expira'] = timezone.now() + timedelta(seconds=int(expira_en))
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
            logger.error('Satrack consulta: no se pudo contactar la API: %s', e)
            return {'error': True, 'mensaje': f'No se pudo contactar la API de ubicación de Satrack: {e}'}

        if respuesta.status_code == 401:
            if reintento:
                reautenticado = self.autenticar()
                if reautenticado['error']:
                    return reautenticado
                return self._consultar(query, extraer, reintento=False)
            return {'error': True, 'mensaje': 'El token de Satrack no es válido o ya expiró'}

        if respuesta.status_code == 400:
            return {'error': True, 'mensaje': 'Alguna placa consultada no pertenece a la cuenta Satrack'}

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
