"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

import pathlib
from collections import namedtuple

from .constant import CONTEXT_TYPE, PREFIX_MENU
from .utils import merge_dict

_file_name = pathlib.Path(__file__).stem

RemixContext = namedtuple("RemixContext", ["address", "port"])


def get_context_inputs() -> dict[str, dict[str, tuple[str, dict]]]:
    return {"required": {"context": (CONTEXT_TYPE, {"forceInput": True})}}


def get_enabled_inputs() -> dict[str, dict[str, tuple[str, dict]]]:
    return {"required": {"enable_this_node": ("BOOLEAN", {"default": True})}}


def get_remix_api_inputs() -> dict[str, dict[str, tuple[str, dict]]]:
    return {
        "required": {"address": ("STRING", {"forceInput": True}), "port": ("INT", {"forceInput": True})},
    }


def wrap_input_types_with(func, input_fn):
    """Decorator to wrap the INPUT_TYPES classmethod and add context input"""

    def wrapper(*args, **kwargs):
        return merge_dict(input_fn(), func())

    return wrapper


class ContextExecutionFuncWrapper:
    """Decorator to wrap the execution function providing context and passing it through"""

    def __init__(self, func):
        self.func = func

    def __get__(self, instance, owner):
        def wrapper(*args, **kwargs):
            # store on instance in case node needs access
            instance.context: RemixContext = kwargs.pop("context")  # noqa
            instance.enable_this_node: bool = kwargs.pop("enable_this_node")  # noqa, we don't return this as output
            return (instance.context,) + self.func(instance, *args, **kwargs)

        return wrapper


def add_context_outputs(cls):
    """Node class decorator for adding context outputs"""
    # add it as first return item (will also usually be first input alphabetically)
    cls.RETURN_TYPES = (CONTEXT_TYPE,) + getattr(cls, "RETURN_TYPES", ())
    cls.RETURN_NAMES = ("context",) + getattr(cls, "RETURN_NAMES", ())
    # this one is optional
    if hasattr(cls, "OUTPUT_IS_LIST"):
        cls.OUTPUT_IS_LIST = (False,) + getattr(cls, "OUTPUT_IS_LIST", ())
    return cls


def add_context_input_enabled_and_output(cls):
    """
    Node class decorator for adding context inputs and outputs.

    This should seamlessly wrap a comfy node class and take care of
    creating the context input and output and piping it through the
    node. Access it using self.context within the execution func.
    """
    add_context_outputs(cls)

    # wrap input types func
    setattr(cls, "INPUT_TYPES", wrap_input_types_with(cls.INPUT_TYPES, get_context_inputs))  # noqa
    setattr(cls, "INPUT_TYPES", wrap_input_types_with(cls.INPUT_TYPES, get_enabled_inputs))  # noqa

    # wrap execution function
    function_name = getattr(cls, "FUNCTION")  # noqa
    func = getattr(cls, function_name)
    wrapped_func = ContextExecutionFuncWrapper(func)
    setattr(cls, function_name, wrapped_func)

    return cls


class RestAPIDetails:
    """Provide the port information to connect to the RTX Remix Toolkit"""

    @classmethod
    def INPUT_TYPES(cls):  # noqa N802
        return {
            "required": {
                "address": ("STRING", {"multiline": False, "default": "127.0.0.1"}),
                "port": (
                    "INT",
                    {
                        "default": 8011,
                        "min": 0,  # Minimum value
                        "max": 65353,  # Maximum value
                        "step": 1,  # Slider's step
                        "display": "number",  # Cosmetic only: display as "number" or "slider"
                    },
                ),
            },
        }

    RETURN_TYPES = ("STRING", "INT")
    RETURN_NAMES = ("address", "port")

    FUNCTION = "get_address"

    CATEGORY = f"{PREFIX_MENU}/{_file_name}"

    def get_address(self, address, port):
        return address, port


@add_context_outputs
class StartContext:
    """Use this node to begin a graph, then pass context along to determine execution order."""

    @classmethod
    def INPUT_TYPES(cls):  # noqa N802
        return {"required": {"address": ("STRING", {"forceInput": True}), "port": ("INT", {"forceInput": True})}}

    RETURN_TYPES = ()
    RETURN_NAMES = ()

    FUNCTION = "execute"

    CATEGORY = f"{PREFIX_MENU}/{_file_name}"

    def execute(self, address, port):
        return (RemixContext(address, port),)


class EndContext:
    """Put this node at the end of your graph to evaluate prior nodes"""

    @classmethod
    def INPUT_TYPES(cls):  # noqa N802
        return {"required": {"context": (CONTEXT_TYPE, {"forceInput": True})}}

    RETURN_TYPES = ()
    RETURN_NAMES = ()

    FUNCTION = "execute"

    CATEGORY = f"{PREFIX_MENU}/{_file_name}"

    OUTPUT_NODE = True

    def execute(self, context):
        return ()


class StringConstant:
    """Declare a string constant"""

    @classmethod
    def INPUT_TYPES(cls):  # noqa N802
        return {
            "required": {
                "string": ("STRING", {"default": "", "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "get_string"
    CATEGORY = f"{PREFIX_MENU}/{_file_name}"

    def get_string(self, string):
        return (string,)


class StringConcatenate:
    """Concatenate two strings"""

    @classmethod
    def INPUT_TYPES(cls):  # noqa N802
        return {
            "required": {
                "string1": ("STRING", {"default": "", "forceInput": True}),
                "string2": ("STRING", {"default": "", "forceInput": True}),
            },
            "optional": {
                "separator": ("STRING", {"default": "_"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "execute"
    CATEGORY = f"{PREFIX_MENU}/{_file_name}"

    def execute(self, string1, string2, separator="_"):
        return (string1 + separator + string2,)


# Hack: string type that is always equal in not equal comparisons
class AnyType(str):
    def __ne__(self, __value: object) -> bool:
        return False


_any = AnyType("*")


class Switch:
    """Switch to one branch or another depending on the bool value"""

    @classmethod
    def INPUT_TYPES(cls):  # noqa N802
        return {
            "required": {
                "if_true": (_any, {}),
                "if_false": (_any, {}),
                "switcher": (
                    "BOOLEAN",
                    {"default": True, "forceInput": True},
                ),
            },
        }

    RETURN_TYPES = (_any,)
    INPUT_IS_LIST = True  # need this or it will crash
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "execute"
    CATEGORY = f"{PREFIX_MENU}/{_file_name}"

    def execute(self, if_true: _any, if_false: _any, switcher: list[bool]):
        return (if_true if switcher[0] else if_false,)


class InvertBool:
    """Invert a boolean value. For example, True to False, or False to True"""

    @classmethod
    def INPUT_TYPES(cls):  # noqa N802
        return {
            "required": {
                "value": (
                    "BOOLEAN",
                    {"default": True, "forceInput": True},
                ),
            },
        }

    RETURN_TYPES = ("BOOLEAN",)
    FUNCTION = "execute"
    CATEGORY = f"{PREFIX_MENU}/{_file_name}"

    def execute(self, value: bool):
        return (not value,)


class StrToList:
    """Convert a string input as a list of strings"""

    @classmethod
    def INPUT_TYPES(cls):  # noqa N802
        return {
            "required": {
                "value": (
                    "STRING",
                    {"forceInput": True},
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    OUTPUT_IS_LIST = (True,)
    FUNCTION = "execute"
    CATEGORY = f"{PREFIX_MENU}/{_file_name}"

    def execute(self, value: str):
        return ([value],)
