from ronnie.apps import AppConfig


class BlogConfig(AppConfig):
    name = "apps.blog"
    verbose_name = "The Blog"

    def ready(self):
        import apps.blog

        apps.blog.EVENTS.append("ready")
