# Generated by Django 5.0.3 on 2024-06-20 16:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("backend", "0003_building_priority_alter_student_gender"),
    ]

    operations = [
        migrations.AddField(
            model_name="building",
            name="capacity_each_room",
            field=models.PositiveSmallIntegerField(
                default=10, verbose_name="Số lượng học viên mỗi phòng"
            ),
        ),
        migrations.AlterField(
            model_name="building",
            name="priority",
            field=models.PositiveSmallIntegerField(
                default=0, verbose_name="Độ ưu tiên (dành cho xếp ưu tiên kí túc xá nữ)"
            ),
        ),
    ]
