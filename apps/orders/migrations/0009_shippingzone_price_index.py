# Dérive préexistante : l'index idx_shippingzone_price est déclaré dans ShippingZone.Meta
# mais n'avait jamais été matérialisé par une migration (détecté par makemigrations --check).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0008_create_outboxevent'),
    ]

    operations = [
        migrations.AddIndex(
            model_name='shippingzone',
            index=models.Index(fields=['price'], name='idx_shippingzone_price'),
        ),
    ]
