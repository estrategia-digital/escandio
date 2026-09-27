"""Check-in periodico de seguimiento (cron).

No hay Celery: este comando lo dispara un cron cada hora
(`0 * * * * python manage.py checkin_periodico`) y decide POR CONTENEDOR si
toca preguntar, segun `Contenedor.checkin_intervalo_horas` (null = desactivado).

Por cada contenedor activo, a cada viaje en curso (despacho aprobado, no
terminado, no anulado, con conductor y salido hoy) le crea una consulta
'¿como va el viaje?' `origen='automatico'`, salvo que:
  - ya tenga una consulta pendiente, o
  - la ultima consulta sea mas reciente que el intervalo configurado.

La consulta la levanta la app en el heartbeat (o al abrir) y el conductor
responde. Mismo modelo/flujo que el trigger manual de Trafico.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone
from django_tenants.utils import schema_context

from contenedor.models import Contenedor

OPCIONES_DEFECTO = ['Todo bien', 'Voy retrasado', 'Tengo un problema']


class Command(BaseCommand):
    help = 'Crea consultas de seguimiento automaticas a los viajes activos.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--contenedor', dest='contenedor', default=None,
            help='Limita a un schema_name (para pruebas). Por defecto: todos.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='No crea nada; solo reporta cuantas consultas se crearian.',
        )

    def handle(self, *args, **opts):
        # Import diferido: modelos de tenant fuera del schema public revientan.
        from ruteo.models.despacho import RutDespacho
        from ruteo.models.seguimiento import RutSeguimiento

        ahora = timezone.now()
        hoy = timezone.localtime(ahora).date()
        dry = opts['dry_run']

        contenedores = Contenedor.objects.exclude(schema_name='public')
        if opts['contenedor']:
            contenedores = contenedores.filter(schema_name=opts['contenedor'])
        # Solo contenedores con el check-in activado.
        contenedores = contenedores.filter(checkin_intervalo_horas__isnull=False)

        total_creadas = 0
        for cont in contenedores:
            intervalo = cont.checkin_intervalo_horas
            if not intervalo or intervalo <= 0:
                continue
            corte = ahora - timedelta(hours=intervalo)
            with schema_context(cont.schema_name):
                activos = RutDespacho.objects.filter(
                    estado_aprobado=True,
                    estado_terminado=False,
                    estado_anulado=False,
                    conductor_id__isnull=False,
                    fecha_salida__date=hoy,
                )
                creadas_cont = 0
                for despacho in activos:
                    if self._debe_saltar(RutSeguimiento, despacho.id, corte):
                        continue
                    if not dry:
                        RutSeguimiento.objects.create(
                            despacho_id=despacho.id,
                            tipo=RutSeguimiento.TIPO_CONSULTA,
                            estado=RutSeguimiento.ESTADO_PENDIENTE,
                            origen=RutSeguimiento.ORIGEN_AUTOMATICO,
                            opciones=OPCIONES_DEFECTO,
                            comentario='¿Cómo va el viaje?',
                        )
                    creadas_cont += 1
                total_creadas += creadas_cont
                if creadas_cont:
                    self.stdout.write(
                        f'{cont.schema_name}: {creadas_cont} consulta(s) '
                        f'(intervalo {intervalo}h){" [dry-run]" if dry else ""}',
                    )

        self.stdout.write(self.style.SUCCESS(
            f'Check-in periodico: {total_creadas} consulta(s) '
            f'{"que se crearian" if dry else "creadas"}.',
        ))

    @staticmethod
    def _debe_saltar(RutSeguimiento, despacho_id, corte):
        """No re-preguntar: hay una pendiente, o la ultima es mas nueva que el
        intervalo."""
        consultas = RutSeguimiento.objects.filter(
            despacho_id=despacho_id, tipo=RutSeguimiento.TIPO_CONSULTA,
        )
        if consultas.filter(estado=RutSeguimiento.ESTADO_PENDIENTE).exists():
            return True
        return consultas.filter(fecha_registro__gte=corte).exists()
