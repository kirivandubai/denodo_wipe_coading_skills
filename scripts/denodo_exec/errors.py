"""The layer's errors: one root, so a tool server can tell a sentence meant for its caller from a
defect, and a refusal kept apart from an unavailability.

A refusal says the input must change before asking again; an unavailability says the same call
may work once the server, the driver or whatever else the agent stands on answers. A model that
reads the sentence needs to know which, and the sentence alone would make it guess.

An agent adopts these classes as its own (``AgentRefused = Refused``) rather than subclassing
them: the layer raises them, and an agent's ``except`` of its own name must catch what the layer
raised — a subclass would not.
"""

from __future__ import annotations


class ExecError(Exception):
    """Base for everything the layer, and an agent built on it, raises on purpose: a sentence
    its caller can hand on."""


class CanonicalError(ExecError):
    """A value has no canonical JSON form: a float, a key that is not a string, a naive
    datetime, an object."""


class Refused(ExecError):
    """Refused before anything moved: an input that does not hold, a statement outside the rule
    of scope, a file that is not a workspace's VQL file. The sentence says what would make it go;
    asking again unchanged never does."""


class Unavailable(ExecError):
    """What the agent stands on did not answer: the Denodo server, the driver, a program. A fact
    about the moment, not about the input."""
