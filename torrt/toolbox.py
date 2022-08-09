import logging

from .base_tracker import GenericPrivateTracker
from .utils import (
    RPCClassesRegistry, TrackerClassesRegistry, config, import_classes
)

if False:  # pragma: nocover
    from .base_rpc import BaseRPC  # noqa
    from .base_tracker import BaseTracker  # noqa

__log__ = logging.getLogger(__name__)


def init_object_registries():
    """Initializes RPC and tracker objects registries with settings from configuration file."""

    __log__.debug('Initializing objects registries from configuration file ...')

    cfg = config.load()

    settings_to_registry_map = {
        'rpc': RPCClassesRegistry
    }

    for settings_entry, registry_cls in settings_to_registry_map.items():

        for alias, settings in cfg[settings_entry].items():
            registry_obj = registry_cls.get(alias)
            registry_obj and registry_obj.spawn_with_settings(settings).register()

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
