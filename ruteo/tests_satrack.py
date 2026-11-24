"""Integracion Satrack: cliente (auth + last) y servicio de refresco.

Sin credenciales reales: requests.post esta mockeado. Cubre cache de token,
reintento 401, error 400, parseo y actualizacion de RutVehiculo.

Correr: python manage.py test ruteo.tests_satrack
"""
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from django_tenants.test.cases import TenantTestCase

from contenedor.models import CtnSatrackConexion
from mensajeria.servicios.cifrado import CifradoServicio
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
    def _conexion(self, con_token=False):
        datos = {
            'contenedor': self.tenant,
            'client_id': 'cliente-1',
            'client_secret_cifrado': CifradoServicio.cifrar('secreto'),
            'grant_type': 'client_credentials',
        }
        if con_token:
            datos['access_token_cifrado'] = CifradoServicio.cifrar('TOK')
            datos['token_expira'] = timezone.now() + timedelta(hours=2)
        return CtnSatrackConexion.objects.create(**datos)

    def _despacho_dispatcher(self, respuestas_por_url):
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
    def test_autenticar_cachea_token_cifrado(self, mock_post):
        mock_post.side_effect = self._despacho_dispatcher({'Keycloak': respuesta_auth()})
        conexion = self._conexion()

        resultado = SatrackCliente(conexion).autenticar()

        self.assertFalse(resultado['error'])
        conexion.refresh_from_db()
        self.assertEqual(CifradoServicio.descifrar(conexion.access_token_cifrado), 'TOK')
        self.assertIsNotNone(conexion.token_expira)
        self.assertEqual(mock_post.call_count, 1)

    @patch('utilidades.satrack.requests.post')
    def test_token_vigente_no_reautentica(self, mock_post):
        mock_post.side_effect = self._despacho_dispatcher({'location': respuesta_last([])})
        conexion = self._conexion(con_token=True)

        SatrackCliente(conexion).ultima_ubicacion(['ABC123'])

        urls = [llamada.args[0] for llamada in mock_post.call_args_list]
        self.assertTrue(all('location' in url for url in urls))
        self.assertEqual(len(urls), 1)

    @patch('utilidades.satrack.requests.post')
    def test_ultima_ubicacion_parsea_eventos(self, mock_post):
        evento = {'serviceCode': 'ABC123', 'latitude': 4.65, 'longitude': -74.1}
        mock_post.side_effect = self._despacho_dispatcher({'location': respuesta_last([evento])})
        conexion = self._conexion(con_token=True)

        resultado = SatrackCliente(conexion).ultima_ubicacion(['ABC123'])

        self.assertFalse(resultado['error'])
        self.assertEqual(resultado['eventos'][0]['serviceCode'], 'ABC123')

    @patch('utilidades.satrack.requests.post')
    def test_401_reautentica_y_reintenta(self, mock_post):
        mock_post.side_effect = self._despacho_dispatcher({
            'Keycloak': respuesta_auth(),
            'location': [RespuestaFalsa(401, {}), respuesta_last([{'serviceCode': 'ABC123', 'latitude': 1, 'longitude': 2}])],
        })
        conexion = self._conexion(con_token=True)

        resultado = SatrackCliente(conexion).ultima_ubicacion(['ABC123'])

        self.assertFalse(resultado['error'])
        urls = [llamada.args[0] for llamada in mock_post.call_args_list]
        self.assertTrue(any('Keycloak' in url for url in urls))

    @patch('utilidades.satrack.requests.post')
    def test_400_placa_no_pertenece(self, mock_post):
        mock_post.side_effect = self._despacho_dispatcher({'location': RespuestaFalsa(400, {})})
        conexion = self._conexion(con_token=True)

        resultado = SatrackCliente(conexion).ultima_ubicacion(['XXX999'])

        self.assertTrue(resultado['error'])
        self.assertIn('no pertenece', resultado['mensaje'])


class SatrackServicioTests(SatrackTestsBase):
    def _vehiculo_en_ruta(self, placa='ABC123'):
        vehiculo = RutVehiculo.objects.create(placa=placa)
        RutDespacho.objects.create(vehiculo=vehiculo, estado_aprobado=True)
        return vehiculo

    @patch('utilidades.satrack.requests.post')
    def test_refrescar_actualiza_vehiculo(self, mock_post):
        evento = {'serviceCode': 'ABC123', 'latitude': 4.711, 'longitude': -74.072, 'speed': 30}
        mock_post.side_effect = self._despacho_dispatcher({'location': respuesta_last([evento])})
        self._conexion(con_token=True)
        vehiculo = self._vehiculo_en_ruta()

        resultado = SatrackUbicacionServicio.refrescar()

        self.assertFalse(resultado['error'])
        self.assertEqual(len(resultado['posiciones']), 1)
        vehiculo.refresh_from_db()
        self.assertEqual(float(vehiculo.latitud), 4.711)
        self.assertEqual(float(vehiculo.longitud), -74.072)

    @patch('utilidades.satrack.requests.post')
    def test_refrescar_marca_conexion_activa(self, mock_post):
        mock_post.side_effect = self._despacho_dispatcher({'location': respuesta_last([])})
        self._conexion(con_token=True)
        self._vehiculo_en_ruta()

        SatrackUbicacionServicio.refrescar()

        conexion = SatrackUbicacionServicio.conexion_actual()
        self.assertEqual(conexion.estado, CtnSatrackConexion.ESTADO_ACTIVO)
        self.assertIsNotNone(conexion.fecha_ultima_consulta)

    @patch('utilidades.satrack.requests.post')
    def test_ttl_evita_consulta_repetida(self, mock_post):
        conexion = self._conexion(con_token=True)
        conexion.fecha_ultima_consulta = timezone.now()
        conexion.save(update_fields=['fecha_ultima_consulta'])
        self._vehiculo_en_ruta()

        resultado = SatrackUbicacionServicio.refrescar()

        self.assertTrue(resultado['cache'])
        mock_post.assert_not_called()

    @patch('utilidades.satrack.requests.post')
    def test_sin_conexion_devuelve_error(self, mock_post):
        self._vehiculo_en_ruta()

        resultado = SatrackUbicacionServicio.refrescar()

        self.assertTrue(resultado['error'])
        mock_post.assert_not_called()

    @patch('utilidades.satrack.requests.post')
    def test_sin_vehiculos_no_consulta(self, mock_post):
        self._conexion(con_token=True)

        resultado = SatrackUbicacionServicio.refrescar()

        self.assertFalse(resultado['error'])
        self.assertEqual(resultado['posiciones'], [])
        mock_post.assert_not_called()
