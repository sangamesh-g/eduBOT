# Generated by Django 5.1.7 on 2025-04-11 16:06

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0003_alter_choice_options_alter_choice_unique_together_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='choice',
            options={'ordering': ['option_id']},
        ),
        migrations.RemoveField(
            model_name='answer',
            name='selected_choice',
        ),
        migrations.AddField(
            model_name='answer',
            name='selected_option',
            field=models.CharField(blank=True, choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')], max_length=1, null=True),
        ),
        migrations.AddField(
            model_name='choice',
            name='option_id',
            field=models.CharField(choices=[('A', 'A'), ('B', 'B'), ('C', 'C'), ('D', 'D')], default=django.utils.timezone.now, help_text='Option identifier (A, B, C, D)', max_length=1),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='choice',
            name='text',
            field=models.TextField(help_text='Choice text (supports multiple lines)'),
        ),
        migrations.AlterField(
            model_name='question',
            name='text',
            field=models.TextField(help_text='Question text (supports multiple lines)'),
        ),
        migrations.AlterUniqueTogether(
            name='choice',
            unique_together={('question', 'option_id')},
        ),
    ]
