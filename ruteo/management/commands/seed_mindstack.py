from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django_tenants.utils import schema_context

from contenedor.models import Contenedor, User, UsuarioContenedor

CONDUCTORES = [
    ('Carlos', 'Ramirez', '3001112201'),
    ('Luisa', 'Gomez', '3001112202'),
    ('Andres', 'Torres', '3001112203'),
    ('Mariana', 'Lopez', '3001112204'),
    ('Pedro', 'Diaz', '3001112205'),
]

FRANJAS = [('Norte', '#2563eb'), ('Centro', '#16a34a'), ('Sur', '#f59e0b')]

# cond: indice en CONDUCTORES o None (sin asignar); estado del despacho; n visitas;
# cuantas entregadas y cuantas con novedad (el resto quedan pendientes).
DESPACHOS = [
    {'cond': 0, 'estado': 'ruta', 'n': 6, 'entregadas': 2, 'novedad': 1},
    {'cond': 1, 'estado': 'ruta', 'n': 5, 'entregadas': 1, 'novedad': 0},
    {'cond': 2, 'estado': 'ruta', 'n': 7, 'entregadas': 3, 'novedad': 1},
    {'cond': 3, 'estado': 'ruta', 'n': 4, 'entregadas': 0, 'novedad': 0},
    {'cond': None, 'estado': 'pendiente', 'n': 5, 'entregadas': 0, 'novedad': 0},
    {'cond': None, 'estado': 'pendiente', 'n': 4, 'entregadas': 0, 'novedad': 0},
    {'cond': 4, 'estado': 'terminado', 'n': 5, 'entregadas': 5, 'novedad': 0},
    {'cond': 0, 'estado': 'anulado', 'n': 3, 'entregadas': 0, 'novedad': 0},
]

BASE_NUMERO = 9_000_000


class Command(BaseCommand):
    help = (
        'Llena un contenedor con datos de prueba (conductores, vehiculos, franjas, '
        'visitas y despachos en varios estados, incluyendo "en ruta"). Idempotente: '
        'reutiliza lo marcado PRUEBA, no duplica.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--contenedor', default='mindstacklabs')

    def handle(self, *args, **opts):
        from ruteo.models.despacho import RutDespacho
        from ruteo.models.visita import RutVisita
        from ruteo.models.franja import RutFranja
        from ruteo.models.vehiculo import RutVehiculo

        clave = opts['contenedor']
        cont = (
            Contenedor.objects.filter(schema_name=clave).first()
            or Contenedor.objects.filter(nombre__iexact=clave).first()
            or Contenedor.objects.filter(nombre__icontains=clave).first()
        )
        if not cont:
            disponibles = list(
                Contenedor.objects.exclude(schema_name='public')
                .values_list('schema_name', flat=True)
            )
            raise CommandError(f'Contenedor "{clave}" no encontrado. Disponibles: {disponibles}')

        conductores = []
        for i, (nombre, apellido, tel) in enumerate(CONDUCTORES, 1):
            correo = f'prueba.conductor{i}@{cont.schema_name}.test'
            user = User.objects.filter(username=correo).first()
            if not user:
                user = User(
                    username=correo, correo=correo,
                    nombre=f'PRUEBA {nombre}', apellido=apellido, telefono=tel,
                )
                user.set_password('Prueba2026*')
                user.save()
            UsuarioContenedor.objects.get_or_create(
                usuario=user, contenedor=cont,
                defaults={
                    'rol': 'usuario', 'tiene_acceso_web': False,
                    'tiene_acceso_movil': True, 'perfil_movil': 'conductor',
                },
            )
            conductores.append(user)

        creados = {'franjas': 0, 'vehiculos': 0, 'despachos': 0, 'visitas': 0}

        with schema_context(cont.schema_name):
            franjas = []
            for i, (nombre, color) in enumerate(FRANJAS, 1):
                f, nuevo = RutFranja.objects.get_or_create(
                    nombre=f'PRUEBA Zona {nombre}',
                    defaults={'codigo': f'PRB-Z{i}', 'color': color},
                )
                creados['franjas'] += int(nuevo)
                franjas.append(f)

            vehiculos = []
            for i in range(1, 5):
                v, nuevo = RutVehiculo.objects.get_or_create(
                    placa=f'PRB{i:03d}',
                    defaults={'capacidad': 100 * i, 'estado_activo': True, 'estado_asignado': True},
                )
                creados['vehiculos'] += int(nuevo)
                vehiculos.append(v)

            ahora = timezone.now()
            for idx, p in enumerate(DESPACHOS):
                primer_num = BASE_NUMERO + idx * 100 + 1
                existente = (
                    RutVisita.objects.filter(numero=primer_num)
                    .select_related('despacho').first()
                )
                if existente and existente.despacho_id:
                    despacho = existente.despacho
                else:
                    despacho = RutDespacho.objects.create(
                        fecha=ahora,
                        estado_aprobado=True,
                        estado_terminado=(p['estado'] == 'terminado'),
                        estado_anulado=(p['estado'] == 'anulado'),
                        vehiculo=vehiculos[idx % len(vehiculos)],
                        conductor_id=(conductores[p['cond']].id if p['cond'] is not None else None),
                        conductor_telefono=(conductores[p['cond']].telefono if p['cond'] is not None else None),
                    )
                    creados['despachos'] += 1

                franja = franjas[idx % len(franjas)]
                for j in range(p['n']):
                    num = primer_num + j
                    entregada = j < p['entregadas']
                    con_novedad = (not entregada) and (j < p['entregadas'] + p['novedad'])
                    _, nuevo = RutVisita.objects.get_or_create(
                        numero=num,
                        defaults={
                            'despacho': despacho,
                            'tipo': 'entrega',
                            'fecha': ahora,
                            'destinatario': f'PRUEBA Cliente {num}',
                            'destinatario_direccion': f'Calle {10 + j} # {j}-{idx} PRUEBA',
                            'destinatario_telefono': f'30022{idx}{j:02d}',
                            'orden': j + 1,
                            'estado_despacho': True,
                            'estado_entregado': entregada,
                            'estado_novedad': con_novedad,
                            'ciudad_id': None,
                            'franja_id': franja.id,
                            'franja_codigo': franja.codigo,
                        },
                    )
                    creados['visitas'] += int(nuevo)

        self.stdout.write(self.style.SUCCESS(
            f'Seed en "{cont.schema_name}" OK. Conductores: {len(conductores)} '
            f'(reutilizados si ya existian). Nuevos -> franjas: {creados["franjas"]}, '
            f'vehiculos: {creados["vehiculos"]}, despachos: {creados["despachos"]}, '
            f'visitas: {creados["visitas"]}. '
            f'Conductores en ruta esperados: 4.'
        ))
