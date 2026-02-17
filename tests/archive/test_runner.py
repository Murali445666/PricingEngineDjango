from django.test.runner import DiscoverRunner

class UnManagedModelTestRunner(DiscoverRunner):
    """
    Forces 'managed = True' for all models during tests, 
    so Django creates the tables in the test database.
    """
    def setup_test_environment(self, *args, **kwargs):
        from django.apps import apps
        self.unmanaged_models = []
        for app_config in apps.get_app_configs():
            for model in app_config.get_models():
                if not model._meta.managed:
                    model._meta.managed = True
                    self.unmanaged_models.append(model)
        super().setup_test_environment(*args, **kwargs)

    def teardown_test_environment(self, *args, **kwargs):
        super().teardown_test_environment(*args, **kwargs)
        for model in self.unmanaged_models:
            model._meta.managed = False