import logging

from .base_tracker import GenericPrivateTracker
from .utils import TrackerClassesRegistry, config, import_classes

if False:  # pragma: nocover
    from .base_tracker import BaseTracker  # noqa

__log__ = logging.getLogger(__name__)


def init_object_registries():
    """Initializes RPC and tracker objects registries with settings from configuration file."""

    __log__.debug('Initializing objects registries from configuration file ...')

    cfg = config.load()

    # Special case for trackers to initialize public trackers automatically.
    for alias, tracker_cls in TrackerClassesRegistry.get().items():

        settings = cfg['trackers'].get(alias)

        if settings is None:

            if issubclass(tracker_cls, GenericPrivateTracker):
                # No use in registering a private tracker without credentials.
                continue

            # Considered public tracker. Use default settings.

        tracker_cls.spawn_with_settings(settings or {}).register()


def bootstrap():
    """Bootstraps torrt environment,
    Populates RPC and Trackers registries with objects instantiated with settings from config.

    """
    __log__.debug('Bootstrapping torrt environment ...')

    import_classes()
    init_object_registries()
