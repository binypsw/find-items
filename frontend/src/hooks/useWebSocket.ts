import { useEffect } from "react";
import { createRunWebSocket } from "../api/client";
import type { RunEvent } from "../types";

export function useWebSocket(onEvent: (e: RunEvent) => void): void {
  useEffect(() => {
    const ws = createRunWebSocket();
    ws.onmessage = (msg) => {
      try {
        onEvent(JSON.parse(msg.data) as RunEvent);
      } catch {
        // ignore malformed messages
      }
    };
    return () => ws.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
