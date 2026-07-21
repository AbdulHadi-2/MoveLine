# Generated manually for Paymera payment method support.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="method",
            field=models.CharField(
                choices=[
                    ("card", "Card"),
                    ("cash", "Cash"),
                    ("partial", "Partial"),
                    ("paymera", "Paymera"),
                ],
                max_length=20,
            ),
        ),
    ]
