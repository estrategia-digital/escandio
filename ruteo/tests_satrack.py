"""Integracion Satrack: cliente (auth + last) y servicio de refresco.

Credenciales desde el entorno (SATRACK_*), requests.post mockeado. Cubre cache
de token en memoria, reintento 401, error 400, parseo y actualizacion de
RutVehiculo, y el caso sin configurar.

Correr: python manage.py test ruteo.tests_satrack
"""
import os
from unittest.mock import patch

from django_tenants.test.cases import TenantTestCase

import ruteo.servicios.satrack as servicio_mod
import utilidades.satrack as cliente_mod
from ruteo.models.despacho import RutDespacho
from ruteo.models.vehiculo import RutVehiculo
from ruteo.servicios.satrack import SatrackUbicacionServicio
from utilidades.satrack import SatrackCliente


class RespuestaFalsa:
    def __init__(self, status_code, cuerpo):
        self.status_code = status_code
        self._cuerpo = cuerpo

    def json(self):
        return self._cuerpo


def respuesta_auth(expires_in=7200, token='TOK'):
    return RespuestaFalsa(200, {'access_token': token, 'expires_in': expires_in})


def respuesta_last(eventos):
    return RespuestaFalsa(200, {'data': {'last': eventos}})


class SatrackTestsBase(TenantTestCase):
    def setUp(self):
        super().setUp()
        os.environ['SATRACK_CLIENT_ID'] = 'cliente-1'
        os.environ['SATRACK_CLIENT_SECRET'] = 'secreto'
        os.environ['SATRACK_GRANT_TYPE'] = 'client_credentials'
        cliente_mod._TOKEN = {'valor': None, 'expira': None}
        servicio_mod._ULTIMA_CONSULTA = {}

    def tearDown(self):
        for clave in ('SATRACK_CLIENT_ID', 'SATRACK_CLIENT_SECRET', 'SATRACK_GRANT_TYPE'):
            os.environ.pop(clave, None)
        super().tearDown()

    def _token_vigente(self):
        from datetime import timedelta
        from django.utils import timezone
        cliente_mod._TOKEN = {'valor': 'TOK', 'expira': timezone.now() + timedelta(hours=2)}

    def _dispatcher(self, respuestas_por_url):
        def dispatcher(url, *args, **kwargs):
            for fragmento, respuesta in respuestas_por_url.items():
                if fragmento in url:
                    if isinstance(respuesta, list):
                        return respuesta.pop(0)
                    return respuesta
            raise AssertionError(f'URL no esperada: {url}')
        return dispatcher


class SatrackClienteTests(SatrackTestsBase):
    @patch('utilidades.satrack.requests.post')
    def test_autenticar_cachea_token_en_memoria(self, mock_post):
        mock_post.side_effect = self._dispatcher({'Keycloak': respuesta_auth()})

        resultado = SatrackCliente().autenticar()

        self.assertFalse(resultado['error'])
        self.assertEqual(cliente_mod._TOKEN['valor'], 'TOK')
        self.assertIsNotNone(cliente_mod._TOKEN['expira'])
        self.assertEqual(mock_post.call_count, 1)

    @patch('utilidades.satrack.requests.post')
    def test_token_vigente_no_reautentica(self, mock_post):
        mock_post.side_effect = self._dispatcher({'location': respuesta_last([])})
        self._token_vigente()

        SatrackCliente().ultima_ubicacion(['ABC123'])

        urls = [llamada.args[0] for llamada in mock_post.call_args_list]
        self.assertEqual(len(urls), 1)
        self.assertTrue(all('location' in url for url in urls))

    @patch('utilidades.satrack.requests.post')
    def test_ultima_ubicacion_parsea_eventos(self, mock_post):
        evento = {'serviceCode': 'ABC123', 'latitude': 4.65, 'longitude': -74.1}
        mock_post.side_effect = self._dispatcher({'location': respuesta_last([evento])})
        self._token_vigente()

        resultado = SatrackCliente().ultima_ubicacion(['ABC123'])

        self.assertFalse(resultado['error'])
        self.assertEqual(resultado['eventos'][0]['serviceCode'], 'ABC123')

    @patch('utilidades.satrack.requests.post')
    def test_401_reautentica_y_reintenta(self, mock_post):
        mock_post.side_effect = self._dispatcher({
            'Keycloak': respuesta_auth(),
            'location': [RespuestaFalsa(401, {}), respuesta_last([{'serviceCode': 'ABC123', 'latitude': 1, 'longitude': 2}])],
        })
        self._token_vigente()

        resultado = SatrackCliente().ultima_ubicacion(['ABC123'])

        self.assertFalse(resultado['error'])
        urls = [llamada.args[0] for llamada in mock_post.call_args_list]
        self.assertTrue(any('Keycloak' in url for url in urls))

    @patch('utilidades.satrack.requests.post')
    def test_400_placa_no_pertenece(self, mock_post):
        mock_post.side_effect = self._dispatcher({'location': RespuestaFalsa(400, {})})
        self._token_vigente()

        resultado = SatrackCliente().ultima_ubicacion(['XXX999'])

        self.assertTrue(resultado['error'])
        self.assertIn('no pertenece', resultado['mensaje'])

    def test_sin_credenciales_no_configurado(self):
        for clave in ('SATRACK_CLIENT_ID', 'SATRACK_CLIENT_SECRET'):
            os.environ.pop(clave, None)
        self.assertFalse(SatrackCliente.configurado())


class SatrackServicioTests(SatrackTestsBase):
    def _vehiculo_en_ruta(self, placa='ABC123'):
        vehiculo = RutVehiculo.objects.create(placa=placa)
        RutDespacho.objects.create(vehiculo=vehiculo, estado_aprobado=True)
        return vehiculo

    @patch('utilidades.satrack.requests.post')
    def test_refrescar_actualiza_vehiculo(self, mock_post):
        evento = {'serviceCode': 'ABC123', 'latitude': 4.711, 'longitude': -74.072, 'speed': 30}
        mock_post.side_effect = self._dispatcher({'location': respuesta_last([evento])})
        self._token_vigente()
        vehiculo = self._vehiculo_en_ruta()

        resultado = SatrackUbicacionServicio.refrescar()

        self.assertFalse(resultado['error'])
        self.assertEqual(len(resultado['posiciones']), 1)
        vehiculo.refresh_from_db()
        self.assertEqual(float(vehiculo.latitud), 4.711)
        self.assertEqual(float(vehiculo.longitud), -74.072)

    @patch('utilidades.satrack.requests.post')
    def test_ttl_evita_consulta_repetida(self, mock_post):
        from django.db import connection
        from django.utils import timezone
        servicio_mod._ULTIMA_CONSULTA = {connection.schema_name: timezone.now()}
        self._vehiculo_en_ruta()

        resultado = SatrackUbicacionServicio.refrescar()

        self.assertTrue(resultado['cache'])
        mock_post.assert_not_called()

    @patch('utilidades.satrack.requests.post')
    def test_sin_configurar_devuelve_error(self, mock_post):
        os.environ.pop('SATRACK_CLIENT_SECRET', None)
        self._vehiculo_en_ruta()

        resultado = SatrackUbicacionServicio.refrescar()

        self.assertTrue(resultado['error'])
        mock_post.assert_not_called()

    @patch('utilidades.satrack.requests.post')
    def test_sin_vehiculos_no_consulta(self, mock_post):
        self._token_vigente()

        resultado = SatrackUbicacionServicio.refrescar()

        self.assertFalse(resultado['error'])
        self.assertEqual(resultado['posiciones'], [])
        mock_post.assert_not_called()
