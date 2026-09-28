"""Auditoría de guías (solo lectura) para detectar entregas que "faltan".

En contenedores SIN complemento (import por Excel) no hay una fuente externa
contra la cual conciliar. Pero casi todas las guías "faltantes" ya están en
Ruteo, invisibles: se importaron pero quedaron SUELTAS (pool, sin despacho), o
entraron con datos rotos (número duplicado / malformado). Este comando las
saca a la luz por día, para reemplazar el control manual del cliente.

Uso:
    python manage.py auditoria_guias --contenedor saludtrec --dias 10
    python manage.py auditoria_guias --contenedor energy       # default 7 días

NO modifica nada.
"""
from collections import Counter, defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.utils import timezone
from django_tenants.utils import schema_context

from contenedor.models import Contenedor


class Command(BaseCommand):
    help = ('Audita guías con problema en un contenedor: sueltas (pool, sin '
            'despacho), números duplicados y números malformados. Solo lectura.')

    def add_arguments(self, parser):
        parser.add_argument('--contenedor', required=True,
                            help='schema_name o nombre del contenedor.')
        parser.add_argument('--dias', type=int, default=7,
                            help='Ventana hacia atrás para duplicados/malformados (default 7).')

    def handle(self, *args, **opts):
        ref = opts['contenedor']
        cont = (Contenedor.objects.filter(schema_name=ref).first()
                or Contenedor.objects.filter(nombre__iexact=ref).first()
                or Contenedor.objects.filter(nombre__icontains=ref).first())
        if not cont:
            disponibles = ', '.join(
                Contenedor.objects.exclude(schema_name='public')
                .values_list('schema_name', flat=True)[:30])
            raise CommandError(f'No encontré el contenedor "{ref}". Disponibles: {disponibles}')

        dias = max(1, opts['dias'])
        corte = timezone.now() - timedelta(days=dias)
        with schema_context(cont.schema_name):
            from ruteo.models.visita import RutVisita
            self._auditar(RutVisita, cont.schema_name, corte, dias)

    def _auditar(self, RutVisita, schema, corte, dias):
        loc = timezone.localtime
        w = self.stdout.write
        w(self.style.MIGRATE_HEADING(
            f'\n=== AUDITORÍA DE GUÍAS · {schema} · últimos {dias} días ==='))

        # --- 1) Guías SUELTAS (pool: sin despacho) ---------------------------
        # Se distingue el origen: sin despacho_anterior = nunca se asignó (leak
        # del import); con despacho_anterior = se soltó/anuló (puede ser a
        # propósito). Las primeras son las que "faltan" de verdad.
        sueltas = RutVisita.objects.filter(despacho__isnull=True)
        nunca_asignadas = defaultdict(list)   # fecha -> [numeros]
        soltadas = defaultdict(list)
        entregadas_sueltas = []
        for v in sueltas.only('numero', 'fecha', 'estado_entregado',
                              'despacho_anterior_id'):
            dia = loc(v.fecha).date().isoformat() if v.fecha else 's/fecha'
            if v.estado_entregado:
                entregadas_sueltas.append(v.numero)
            if v.despacho_anterior_id is None:
                nunca_asignadas[dia].append(v.numero)
            else:
                soltadas[dia].append(v.numero)

        total_nunca = sum(len(x) for x in nunca_asignadas.values())
        w(self.style.WARNING(
            f'\n1) GUÍAS SUELTAS SIN ASIGNAR (importadas y nunca despachadas): {total_nunca}'))
        w('   → son las que el conductor nunca vio; el faltante más probable.')
        for dia in sorted(nunca_asignadas):
            nums = sorted(nunca_asignadas[dia])
            w(f'   {dia}: {len(nums)} guías  {nums[:20]}{" …" if len(nums) > 20 else ""}')
        if soltadas:
            tot_s = sum(len(x) for x in soltadas.values())
            w(f'\n   (informativo) soltadas/anuladas en pool (tenían despacho antes): {tot_s}')
            for dia in sorted(soltadas):
                w(f'     {dia}: {len(soltadas[dia])}')
        if entregadas_sueltas:
            w(self.style.ERROR(
                f'   ⚠ {len(entregadas_sueltas)} guías sueltas figuran ENTREGADAS '
                f'(inconsistente): {sorted(entregadas_sueltas)[:20]}'))

        # Longitud "normal" del número de guía (la moda) = ancla para distinguir
        # una guía real de un valor basura (cédula, relleno) metido en el campo.
        numeros = list(RutVisita.objects.filter(fecha__gte=corte)
                       .exclude(numero__isnull=True)
                       .values_list('numero', flat=True))
        longitudes = Counter(len(str(n)) for n in numeros)
        moda_len = longitudes.most_common(1)[0][0] if longitudes else 0

        def _es_guia_real(num):
            return num is not None and len(str(num)) == moda_len

        # --- 2) Números DUPLICADOS (solo guías reales) -----------------------
        # Se excluyen los valores malformados: un mismo relleno (p.ej. '1' o una
        # cédula) aparece en decenas de despachos y ahogaría la señal. Esos van
        # en la sección 3.
        dups = [row for row in (
                    RutVisita.objects.filter(fecha__gte=corte)
                    .values('numero').annotate(c=Count('id'))
                    .filter(c__gt=1, numero__isnull=False).order_by('-c'))
                if _es_guia_real(row['numero'])]
        w(self.style.WARNING(
            f'\n2) GUÍAS DUPLICADAS (mismo número real en 2+ visitas, últimos {dias} días): {len(dups)}'))
        w('   → una guía cargada dos veces: una copia puede quedar sin entregar.')
        for row in dups[:50]:
            copias = list(RutVisita.objects.filter(numero=row['numero'])
                          .values('id', 'despacho_id', 'estado_entregado'))
            det = ', '.join(
                f"v{c['id']}(desp={c['despacho_id']},entr={int(bool(c['estado_entregado']))})"
                for c in copias)
            w(f"   guía {row['numero']} ×{row['c']}: {det}")

        # --- 3) Números MALFORMADOS (longitud distinta a la común) -----------
        malformados = sorted({n for n in numeros if len(str(n)) != moda_len})
        w(self.style.WARNING(
            f'\n3) NÚMEROS MALFORMADOS (longitud ≠ {moda_len} díg., la común) '
            f'(últimos {dias} días): {len(malformados)}'))
        w('   → guías con número roto (cédula/relleno en el campo); no concilian.')
        w(f'   distribución de longitudes: {dict(sorted(longitudes.items()))}')
        for n in malformados[:50]:
            veces = sum(1 for x in numeros if x == n)
            w(f'   {n}  ({len(str(n))} díg., ×{veces})')

        w(self.style.SUCCESS(
            f'\nResumen: {total_nunca} guías sueltas sin asignar · '
            f'{len(dups)} guías duplicadas (reales) · '
            f'{len(malformados)} números malformados.'))
