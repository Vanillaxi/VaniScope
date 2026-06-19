"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { getArtifact } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { openTaskEventSource } from "@/lib/sse";
import type { TaskEvent } from "@/lib/types";

type EventStreamPanelProps = {
  taskId: string;
  onEventsChange?: (events: TaskEvent[]) => void;
};

export function EventStreamPanel({ taskId, onEventsChange }: EventStreamPanelProps) {
  const { language, t } = useI18n();
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);
  const [connectionState, setConnectionState] = useState("connecting");
  const [streamWarning, setStreamWarning] = useState<string | null>(null);
  const connectionStateRef = useRef(connectionState);

  useEffect(() => {
    connectionStateRef.current = connectionState;
  }, [connectionState]);

  useEffect(() => {
    let closed = false;
    let source: EventSource | null = null;
    const seen = new Set<string>();

    const pushEvent = (event: TaskEvent) => {
      const key = event.event_id || `${event.kind}-${event.created_at}`;
      if (seen.has(key)) return;
      seen.add(key);
      setEvents((current) => {
        const next = [...current, event].slice(-80);
        onEventsChange?.(next);
        return next;
      });
    };

    const loadFallback = async () => {
      try {
        const artifact = await getArtifact(taskId, "events.jsonl");
        if (closed) return;
        artifact.content
          .split("\n")
          .filter(Boolean)
          .map((line) => {
            try {
              return JSON.parse(line) as TaskEvent;
            } catch {
              setStreamWarning(t.events.invalidJsonl);
              return null;
            }
          })
          .filter((event): event is TaskEvent => event !== null)
          .forEach(pushEvent);
        setConnectionState("polling");
      } catch {
        if (!closed) setConnectionState("unavailable");
      }
    };

    try {
      source = openTaskEventSource(
        taskId,
        (event) => {
          setConnectionState("live");
          pushEvent(event);
        },
        () => setStreamWarning(t.events.invalidSse),
        () => {
          setConnectionState("polling");
          void loadFallback();
        },
      );
    } catch {
      void loadFallback();
    }

    const interval = window.setInterval(() => {
      if (connectionStateRef.current !== "live") void loadFallback();
    }, 4000);

    return () => {
      closed = true;
      window.clearInterval(interval);
      source?.close();
    };
  }, [onEventsChange, taskId, t.events.invalidJsonl, t.events.invalidSse]);

  const renderedEvents = useMemo(() => [...events].reverse(), [events]);

  return (
    <Card className="p-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{t.events.title}</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {connectionStateLabel(connectionState, t)}
          </p>
        </div>
        <Button variant="secondary" onClick={() => void loadEventsSnapshot(taskId, setEvents)}>
          {t.events.manualRefresh}
        </Button>
      </div>
      {streamWarning ? (
        <div className="mt-4 rounded-md border border-[#fedf89] bg-[#fffaeb] p-3 text-sm text-[#93370d]">
          {streamWarning}
        </div>
      ) : null}
      <div className="mt-4 max-h-[520px] overflow-auto rounded-md border border-[var(--line)]">
        {renderedEvents.length === 0 ? (
          <div className="p-4 text-sm text-[var(--muted)]">{t.events.empty}</div>
        ) : (
          renderedEvents.map((event, index) => {
            const eventKey = event.event_id || `${event.kind}-${event.created_at}-${index}`;
            const expanded = expandedEventId === eventKey;
            return (
              <div
                key={eventKey}
                className="border-b border-[var(--line)] bg-white p-4 last:border-b-0"
              >
                <button
                  type="button"
                  onClick={() => setExpandedEventId(expanded ? null : eventKey)}
                  className="flex w-full flex-col gap-2 text-left"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-md bg-[var(--panel-soft)] px-2 py-1 text-xs font-semibold">
                      {event.kind}
                    </span>
                    <span className="text-xs text-[var(--muted)]">
                      {formatDateTime(event.created_at, language)}
                    </span>
                  </div>
                  <div className="text-sm text-[#26323f]">{event.message}</div>
                </button>
                {expanded ? (
                  <pre className="mt-3 rounded-md bg-[#111827] p-3 text-xs text-[#e5e7eb]">
                    {JSON.stringify(event.payload ?? {}, null, 2)}
                  </pre>
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </Card>
  );
}

async function loadEventsSnapshot(
  taskId: string,
  setEvents: (events: TaskEvent[]) => void,
) {
  const artifact = await getArtifact(taskId, "events.jsonl");
  const events = artifact.content
    .split("\n")
    .filter(Boolean)
    .flatMap((line) => {
      try {
        return [JSON.parse(line) as TaskEvent];
      } catch {
        return [];
      }
    })
    .slice(-80);
  setEvents(events);
}

function connectionStateLabel(
  state: string,
  t: ReturnType<typeof useI18n>["t"],
) {
  if (state === "live") return t.events.live;
  if (state === "polling") return t.events.polling;
  if (state === "unavailable") return t.events.unavailable;
  return t.events.connecting;
}
