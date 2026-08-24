from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('products', '0010_product_average_rating_product_total_reviews_review'),
    ]

    operations = [
        migrations.AlterField(
            model_name='review',
            name='product',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.CASCADE,
                related_name='reviews',
                to='products.product',
                verbose_name='Produit',
            ),
        ),
    ]