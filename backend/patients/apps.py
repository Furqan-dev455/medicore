from django.apps import AppConfig


class PatientsConfig(AppConfig):
    name = 'patients'
    default = True

    def ready(self):
        from . import signals  # noqa: F401
