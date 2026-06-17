from __future__ import annotations

from webscoper.schemas.prompt import RuntimeReminder


class RuntimeReminderStore:
    def __init__(self) -> None:
        self._reminders: list[RuntimeReminder] = []

    def add(self, message: str, level: str = "info", source: str = "runtime") -> None:
        self._reminders.append(
            RuntimeReminder(message=message, level=level, source=source)
        )

    def list(self) -> list[RuntimeReminder]:
        return list(self._reminders)

    def render_xml(self) -> str:
        if not self._reminders:
            return ""

        return "\n".join(
            [
                (
                    f'<system-reminder level="{_xml_escape(reminder.level)}" '
                    f'source="{_xml_escape(reminder.source)}">\n'
                    f"{_xml_escape(reminder.message)}\n"
                    "</system-reminder>"
                )
                for reminder in self._reminders
            ]
        )


def _xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
