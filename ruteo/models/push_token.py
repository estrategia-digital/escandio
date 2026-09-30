from django.db import models


class RutPushToken(models.Model):
    PLATAFORMA_IOS = 'ios'
    PLATAFORMA_WEB = 'web'
    PLATAFORMA_CHOICES = [
        (PLATAFORMA_IOS, 'iOS (APNs)'),
        (PLATAFORMA_WEB, 'Web Push'),
    ]

    usuario_id = models.IntegerField(db_index=True)
    plataforma = models.CharField(max_length=10, choices=PLATAFORMA_CHOICES)
    # iOS: device token de APNs. Web: la suscripción Web Push serializada (JSON).
    token = models.TextField()
    activo = models.BooleanField(default=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rut_push_token"
        ordering = ["-id"]
