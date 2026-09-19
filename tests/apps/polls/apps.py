from ronnie.apps import AppConfig


class ArchiveConfig(AppConfig):
    name = "apps.polls"


class PollsConfig(AppConfig):
    name = "apps.polls"
    label = "poll"
    default = True
