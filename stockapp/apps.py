from django.apps import AppConfig


class StockappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'stockapp'

    def ready(self):
        """
        Enregistrer les signaux lors du démarrage de l'application.
        """
        import stockapp.signals  # noqa: F401
