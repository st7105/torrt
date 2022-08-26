
class TorrtException(Exception):
    """Base torrt exception.
    Other torrt exceptions should inherit from this.

    """


class TorrtTrackerException(TorrtException):
    """Base torrt tracker exception.

    All other tracker related exception should inherit from that.

    """
