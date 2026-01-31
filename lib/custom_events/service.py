"""Reusable custom event service for Fusion add-ins.

Manages registration, firing, and cleanup of Fusion custom events.
Used for deferred actions like dialog relaunch after command closes.
"""

from __future__ import annotations

from collections.abc import Callable

import adsk.core

from ..fusionAddInUtils import handle_error, log


class CustomEventService:
    """Manages multiple custom events with flexible callbacks.

    Usage:
        service = CustomEventService()
        service.register("myEvent", callback=my_function)
        service.fire("myEvent")
        service.stop()  # Cleanup all events
    """

    def __init__(self) -> None:
        self._events: dict[str, _EventRegistration] = {}

    def register(
        self,
        event_id: str,
        callback: Callable[[], None],
    ) -> None:
        """Register a custom event with a callback.

        Args:
            event_id: Unique identifier for this event
            callback: Function to call when event fires
        """
        if event_id in self._events:
            # Already registered - update callback
            self._events[event_id].callback = callback
            return

        app = adsk.core.Application.get()

        # Defensive: unregister if exists from previous session
        try:
            app.unregisterCustomEvent(event_id)  # type: ignore[attr-defined]
        except:
            pass

        # Create handler
        handler = _CustomHandler(event_id, callback)

        # Register event
        custom_event = app.registerCustomEvent(event_id)  # type: ignore[attr-defined]
        custom_event.add(handler)  # type: ignore[union-attr]

        self._events[event_id] = _EventRegistration(
            event_id=event_id,
            custom_event=custom_event,
            handler=handler,
            callback=callback,
        )

    def fire(self, event_id: str, context: str = "") -> None:
        """Fire a registered custom event.

        Args:
            event_id: The event to fire
            context: Optional context string (for future use)
        """
        if event_id not in self._events:
            log(f"CustomEventService: Event '{event_id}' not registered")
            return

        app = adsk.core.Application.get()
        app.fireCustomEvent(event_id, context)  # type: ignore[attr-defined]

    def stop(self) -> None:
        """Unregister all events. Call from add-in stop()."""
        app = adsk.core.Application.get()

        for reg in self._events.values():
            if reg.custom_event and reg.handler:
                reg.custom_event.remove(reg.handler)
            try:
                app.unregisterCustomEvent(reg.event_id)  # type: ignore[attr-defined]
            except:
                pass

        self._events.clear()


class _EventRegistration:
    """Internal: Tracks a registered event and its handler."""

    __slots__ = ("event_id", "custom_event", "handler", "callback")

    def __init__(
        self,
        event_id: str,
        custom_event: "adsk.core.CustomEvent",  # type: ignore[name-defined]
        handler: "_CustomHandler",
        callback: Callable[[], None],
    ) -> None:
        self.event_id = event_id
        self.custom_event = custom_event
        self.handler = handler
        self.callback = callback


# CustomEventHandler exists at runtime but not in type stubs
class _CustomHandler(adsk.core.CustomEventHandler):  # type: ignore[name-defined]
    """Internal handler that invokes the registered callback."""

    def __init__(self, event_id: str, callback: Callable[[], None]) -> None:
        super().__init__()
        self._event_id = event_id
        self._callback = callback

    def notify(self, args: "adsk.core.CustomEventArgs") -> None:  # type: ignore[name-defined]
        """Execute callback when event fires."""
        try:
            self._callback()
        except:
            handle_error(f"CustomEventService.{self._event_id}")
