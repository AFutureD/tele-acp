import inspect
from typing import Any, Callable

from pydantic import BaseModel, typing
from tele_acp_core import AnyFunction, ChatMessage, Command, CommandExecutable
from tele_acp_core.command import Context


def find_parameter_name(fn: Callable[..., Any], the_type: type) -> str | None:
    """Find the parameter that should receive the Context object.

    Searches through the function's signature to find a parameter
    with a Context type annotation.

    Args:
        fn: The function to inspect
        the_type: The type of the context parameter

    Returns:
        The name of the context parameter, or None if not found
    """

    # Get type hints to properly resolve string annotations
    try:
        hints = typing.get_type_hints(fn)
    except Exception:
        # If we can't resolve type hints, we can't find the context parameter
        return None

    # Check each parameter's type hint
    for param_name, annotation in hints.items():
        # Handle direct Context type
        if inspect.isclass(annotation) and issubclass(annotation, the_type):
            return param_name

        # Handle generic types like Optional[Context]
        origin = typing.get_origin(annotation)
        if origin is not None:
            args = typing.get_args(annotation)
            for arg in args:
                if inspect.isclass(arg) and issubclass(arg, the_type):
                    return param_name

    return None


def find_value_on_dict_by_type(d: dict, the_type: type) -> Any | None:
    """Find a value in the dictionary that matches the given type."""

    for value in d.values():
        if isinstance(value, the_type):
            return value
    return None


class CommandInfo(BaseModel):
    name: str
    description: str
    fn: AnyFunction
    context_kwargs: dict[type, str] = {}

    def __call__(self, *args) -> Any:
        return self.fn(*args)


class CommandCenter(CommandExecutable):
    def __init__(self) -> None:
        self._registered_commands: dict[str, CommandInfo] = {}
        self.register_command(self.show_help, name="help", description="show help message")

    def get_command(self, name: str) -> CommandInfo | None:
        return self._registered_commands.get(name)

    async def can_execute(self, name: str) -> bool:
        return name in self._registered_commands

    async def execute_command(self, name: str, *args, **kwargs) -> Any:
        name = name.strip()
        command = self.get_command(name)
        if not command:
            raise ValueError(f"command not found: {name}")

        message = find_value_on_dict_by_type(kwargs, ChatMessage)
        if message is None:
            raise ValueError("ChatMessage parameter is required to execute command")

        context = Context(message=message)

        context_kwargs = {}
        if param_name := command.context_kwargs.get(Context):
            context_kwargs[param_name] = context
        if param_name := command.context_kwargs.get(ChatMessage):
            context_kwargs[param_name] = message

        result = command(*args, **context_kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    def command(self, name: str | None = None, description: str | None = None) -> Callable[[AnyFunction], AnyFunction]:
        def decorator(fn: AnyFunction) -> AnyFunction:
            self.register_command(fn, name=name, description=description)
            return fn

        return decorator

    def register(self, command: Command, scope: str | None = None) -> CommandInfo:
        return self.register_command(command.fn, name=command.name, description=command.description, scope=scope)

    def register_command(self, fn: AnyFunction, *, name: str | None = None, description: str | None = None, scope: str | None = None) -> CommandInfo:
        name = name or fn.__name__  # ty:ignore[unresolved-attribute]
        if name == "<lambda>":
            raise ValueError("You must provide a name for lambda functions")

        command_name = f"{scope}.{name}" if scope else name
        if command_name in self._registered_commands:
            raise ValueError(f"command already registered: {command_name}")

        description = description or inspect.getdoc(fn) or ""

        context_kwargs: dict[type, str] = {}
        if key := find_parameter_name(fn, ChatMessage):
            context_kwargs[ChatMessage] = key
        if key := find_parameter_name(fn, Context):
            context_kwargs[Context] = key

        command = CommandInfo(fn=fn, name=command_name, description=description, context_kwargs=context_kwargs)
        self._registered_commands[command_name] = command
        return command

    async def show_help(self) -> str:
        lines = [f"/{command.name}: {command.description}" for command in self._registered_commands.values()]
        return "\n".join(lines)


command_center = CommandCenter()
