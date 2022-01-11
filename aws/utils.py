from inspect import signature
import inspect
from typing import Sequence
# import aws_cdk.core as cdk
from aws_cdk import (
    Duration,
    Stack,
)
from constructs import Construct


def gen_name(scope: Construct, id: str):
    stack = Stack.of(scope)
    # stack = [_ for _ in scope.node.scopes if core.Stack.is_stack(_)][0]
    return f"{stack.stack_name}-{id}"


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
    [kwargs.pop(p) for p in params]