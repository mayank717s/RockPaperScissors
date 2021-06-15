# -*- coding: utf-8 -*-

import datetime
import pkg_resources
import shelve

__all__ = ["Scorekeeper", "score"]


class _ScorekeeperSharedState(object):
    """This class manages the shared state held between all instances of any
    child class of Scorekeeper. It implments the "Borg pattern" described at
    http://code.activestate.com/recipes/66531/.

    """
    _shared_state = {}

    def __init__(self):
        self.__dict__ = _ScorekeeperSharedState._shared_state.setdefault(type(self), {})


class Scorekeeper(_ScorekeeperSharedState):
    """Scorekeeper is generally used as a superclass, with subclasses being
    able to isolate state (score) and having the ability to be configured with
    defaults. That being said, it's definitely possible to just use the
    Scorekeeper class in very simple applications where, for example, only
    a single state needs to be maintained. This can cause complications, especially
    if the package is not used in an isolated environment such as a virtualenv.

    A Scorekeeper object accumulates *points* and stores them as a *score*. It
    can have a *decay* which is the number of seconds it takes for a point of
    score to decay. Finally, it has a *threshold* which is the score that must be
    exceeded in order to perform a *callback*.

    Examples:
        >>> scorekeeper = Scorekeeper()
        >>> scorekeeper.score
        0
        >>> scorekeeper(10)
        >>> scorekeeper.score
        10

        >>> @score(Scorekeeper, 10)
        >>> def check_api():
        ...    if not api_call().successful:
        ...        return False
        ...    return True
        ...
        >>> scorekeeper = Scorekeeper()
        >>> scorekeeper.score
        0
        >>> check_api()
        False
        >>> scorekeeper.score
        10

    Commonly overriden attributes for subclesses of Scorekeeper are:
        * default_threshold
        * default_decay
        * default_callback

    Attributes:
        default_threshold (int): The default threshold which is the score that needs
            to be exceeded in order for the provided callback to be called.
        default_decay (int, float): The default decay which is the number of seconds
            it takes for the score to be reduced by 1 point. For example, if the
            current score is 20 and the decay is 5, after 5 seconds the score will
            be 19 and after 10 seconds the score will be 18, etc. This is optional.

    Args:
        threshold (int): Replaces any default threshold. Optional.
        decay (int, float): Replaces any default decay. Optional.
        callback (callable): Is called when threshold is exceeded, otherwise raises
            a ScoreExceededError. Optional.

    """
    default_threshold = 100
    default_decay = None

    def __init__(self):
        _ScorekeeperSharedState.__init__(self)
        self.score = self._get_score()[1]

    def __call__(self, score, threshold=None, decay=None, callback=None):
        if not threshold:
            threshold = self.default_threshold
        if not decay:
            decay = self.default_decay
        if not callback:
            callback = self.default_callback
        return_value = None
        self.score = self._get_score()[1]
        if decay:
            self._decay(decay)
        self.score += score
        if self.score > threshold:
            self.reset_score()
            return_value = self.default_callback() if not callback else callback()
        self._set_score()
        return return_value

    def default_callback(self):
        """The default callback that is called when the score exceeds the threshold."""
        raise ScoreExceededError("Score has been exceeded!")

    def reset_score(self):
        """Reset score to 0 and persist to the filesystem."""
        self.score = 0
        self._set_score()

    def _get_score(self):
        db = shelve.open(self._shelve_path())
        key = type(self).__name__
        result = db.get(key) or {}
        db.close()
        return result.get("datetime"), result.get("score", 0)

    def _set_score(self):
        db = shelve.open(self._shelve_path())
        key = type(self).__name__
        db[key] = {"datetime": datetime.datetime.now(), "score": self.score}
        db.close()

    def _shelve_path(self):
        return pkg_resources.resource_filename('scorekeeper', 'data/scores')

    def _decay(self, rate):
        time = self._seconds_since_last_score()
        decay = int(time / rate)
        self.score = max(0, self.score - decay)

    def _seconds_since_last_score(self):
        last_time = self._get_score()[0]
        if not last_time:
            return 0
        else:
            return (datetime.datetime.now() - last_time).seconds


class ScoreExceededError(Exception):
    pass


def score(scorekeeper_class, points, **kwargs):
    """Execute the decorated function and add points to the provided
    Scorekeeper's score if the function returns Falsey, otherwise do nothing.

    args:
        scorekeeper_class (:obj:`Scorekeeper`): A Scorekeeper or subclass of
            Scorekeeper that will be used to store the score.
        points (int): The number of points that will be added to the score of
            scorekeeper_class if the decorated function returns Falsey.
        **kwargs: Arbitrary arguments that are passed to the scorekeeper_class
            __call__ method.
    """

    def decorator(func):

        def wrapper(*args):
            if not func():
                obj = scorekeeper_class()
                obj(points, **kwargs)

        return wrapper

    return decorator
