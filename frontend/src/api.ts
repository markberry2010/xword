import type { PuzzleData, ProgressEvent } from "./types";

export function generatePuzzle(
  difficulty: string,
  onProgress: (event: ProgressEvent) => void,
  onComplete: (puzzle: PuzzleData, costCents: number | null) => void,
  onError: (message: string) => void
): () => void {
  const abortController = new AbortController();

  const url = `/api/generate?difficulty=${encodeURIComponent(difficulty)}`;

  fetch(url, { signal: abortController.signal })
    .then(async (response) => {
      if (!response.ok) {
        onError(`Server error: ${response.status}`);
        return;
      }
      const reader = response.body?.getReader();
      if (!reader) {
        onError("No response stream");
        return;
      }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE events are separated by double newlines
        const parts = buffer.split(/\r?\n\r?\n/);
        // Last part may be incomplete — keep it in buffer
        buffer = parts.pop() || "";

        for (const block of parts) {
          let eventType = "";
          let eventData = "";

          for (const line of block.split(/\r?\n/)) {
            if (line.startsWith("event:")) {
              eventType = line.slice(6).trim();
            } else if (line.startsWith("data:")) {
              eventData = line.slice(5).trim();
            }
          }

          if (!eventType || !eventData) continue;

          try {
            const parsed = JSON.parse(eventData);
            if (eventType === "progress") {
              onProgress(parsed as ProgressEvent);
            } else if (eventType === "complete") {
              onComplete(parsed.puzzle ?? parsed as PuzzleData, parsed.cost_cents ?? null);
            } else if (eventType === "error") {
              onError(parsed.message || "Unknown error");
            }
          } catch {
            // skip malformed events
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== "AbortError") {
        onError(err.message || "Network error");
      }
    });

  return () => abortController.abort();
}
