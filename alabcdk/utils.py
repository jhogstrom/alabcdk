from inspect import signature
import inspect
from typing import Sequence
# import aws_cdk.core as cdk
from aws_cdk import (
    Duration,
    Stack
)
import aws_cdk as cdk
from constructs import Construct
import uuid
import logging
import os
import sys

_DEFAULT_LOGLEVEL = "INFO"

def gen_name(
        scope: Construct,
        id: str,
        *,
        globalize: bool = False,
        all_lower: bool = False,
        clean_string: bool = False):
    stack = Stack.of(scope)
    result = f"{stack.stack_name}-{id}"

    if globalize and hasattr(stack, "stage"):
        if stack.stage is not None:
            result += "-" + stack.stage
        # if stack.stage != "PROD":
        #     result += "-" + stack.user

    if all_lower:
        result = result.lower()

    if clean_string:
        result = result.replace("_", "-").replace(".", "-")

    return result


def generate_output(scope, name: str, value):
    cdk.CfnOutput(scope, "X"+str(uuid.uuid4()), value=f"{name}={value}")


def stage_based_removal_policy(scope) -> cdk.RemovalPolicy:
    stack = Stack.of(scope)
    if hasattr(stack, "stage"):
        if stack.stage == "PROD":
            return cdk.RemovalPolicy.RETAIN
    return cdk.RemovalPolicy.DESTROY


def get_params(allvars: dict) -> dict:
    """
    Filters all parameters that are KEYWORD_ONLY from allvars (retrieved by locals()),
    combines them with kwargs (found in allvars) and returns the resulting dict.

    This helps getting all the parameters to a function (e.g. __init__)
    into a dictionary to handle them uniformly.

    Parameters in the global list non_passthrough_names will NOT be included in the result.
    This avoids passing those parameters to super.__init__(..., **kwargs)

    Example usage:
    >>>class foo():
    ...   def __init__(self, a, b, *, c=3, d=4, **kwargs):
    ...      print(get_params(locals()))
    >>>foo("a", "b", d="DDD", foobar="baz")
    {c: 3, d: "DDD", foobar: "baz"}

    :param locals: Dictionary with local variables
    :return: Combined dictionary
    """
    assert(allvars.get("self"))
    assert("kwargs" in allvars)
    kwargs = allvars.get("kwargs")
    kwargs = kwargs or {}
    cls = type(allvars["self"])
    parameters = signature(cls.__init__).parameters
    return {**{k: v for (k, v) in allvars.items()
            if parameters.get(k)
            and parameters[k].kind == parameters[k].KEYWORD_ONLY}, **kwargs}


def filter_kwargs(kwargs: dict, filter: str) -> dict:
    """
    Filter the dictionary including only keys starting with filter.
    The resulting dictionary will have the filter string removed from the keys.

    :param kwargs: Dictionary to filter
    :param filter: string to filter on
    :return: Filtered dictionary with renamed keys

    Example:
    >>>d = {"a_b": 1, "a_c": 2, "b_abc": "abc"}
    >>>print(filter_kwargs(d, "a_"))
    {'b': 1, 'c': 2}
    >>>print(filter_kwargs(d, "b_"))
    {'abc': 'abc'}
    """
    return {k.replace(filter, "", 1): v for (k, v) in kwargs.items() if k.startswith(filter)}

def remove_params(kwargs: dict, params: Sequence[str]):
    """
    Remove entries from a dictionary

    Will yield KeyError if an entry in params is not in kwargs,
    but that is a good thing and indicates a coding error.

    Args:
        kwargs (dict): Dictionary from which to remove entries.
        params (Sequence[str]): Entries to remove
    """
    [kwargs.pop(p) for p in params]

def setup_logger(
        *,
        name: str = None,
        level: int = None,
        formatstr: str = None) -> logging.Logger:
    logger = logging.getLogger(name)
    if level is None:
        level = logging.getLevelName(os.environ.get("LOGLEVEL", _DEFAULT_LOGLEVEL))
    if any([_.name == name for _ in logger.handlers]):
        logger.info(f"Handler {name} already initialized")
        return logger

    formatstr = formatstr or '%(asctime)s | %(levelname)-8s | %(message)s'
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stderr)
    handler.name = name
    handler.setLevel(level)
    formatter = logging.Formatter(formatstr)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    # logger.propagate = False  # Prevent duplicate loglines in cloud watch
    if isinstance(level, int):
        level = logging.getLevelName(level)
    logger.info(f"Configured logger '{name}' with level {level}.")
    return logger