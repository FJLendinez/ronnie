from ronnie.apps import AppConfig


class OtherConfig(AppConfig):
    name = "apps.other"
    label = "blog"  # deliberately collides with apps.blog
