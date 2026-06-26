# Utils Model

from django.db import models



class ModelApi(models.Model):
    
    created = models.DateTimeField(
        'created at',
        auto_now_add=True,
        help_text='Fecha de creacion.'
    )

    modified = models.DateTimeField(
        'modified at',
        auto_now_add=True,
        help_text='Fecha de modificacion.'
    )


    class Meta:
        abstract = True,
        ordering = ['-created', '-modified']
