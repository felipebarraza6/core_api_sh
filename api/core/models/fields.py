"""Custom model fields for timezone-aware datetime handling."""

from django.db import models
from django.utils import timezone
from django.conf import settings


class AwareDateTimeField(models.DateTimeField):
    """
    DateTimeField that silently converts naive datetimes to timezone-aware
    using the project's default timezone, avoiding RuntimeWarning spam.
    """

    def get_prep_value(self, value):
        value = self.to_python(value)
        if (
            value is not None
            and settings.USE_TZ
            and timezone.is_naive(value)
        ):
            value = timezone.make_aware(value, timezone.get_default_timezone())
        return super().get_prep_value(value)
