import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contenedor', '0018_habilitar_seguimiento_mindstacklabs'),
    ]

    operations = [
        migrations.AddField(
            model_name='contenedor',
            name='acceso_satrack',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='CtnSatrackConexion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('client_id', models.CharField(max_length=255)),
                ('client_secret_cifrado', models.TextField()),
                ('grant_type', models.CharField(default='client_credentials', max_length=50)),
                ('access_token_cifrado', models.TextField(null=True)),
                ('token_expira', models.DateTimeField(null=True)),
                ('fecha_ultima_consulta', models.DateTimeField(null=True)),
                ('estado', models.CharField(choices=[('pendiente', 'Pendiente'), ('activo', 'Activo'), ('error', 'Error')], default='pendiente', max_length=20)),
                ('error_mensaje', models.TextField(blank=True, null=True)),
                ('fecha_conexion', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
                ('contenedor', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='satrack_conexion', to='contenedor.contenedor')),
            ],
            options={
                'db_table': 'ctn_satrack_conexion',
            },
        ),
    ]
