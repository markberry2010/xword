import type { PuzzleData, ProgressEvent } from "./types";

export function generatePuzzle(
  difficulty: string,
  size: number,
  onProgress: (event: ProgressEvent) => void,
  onComplete: (puzzle: PuzzleData, costCents: number | null) => void,
  onError: (message: string) => void
): () => void {
  const abortController = new AbortController();

  const url = `/api/generate?difficulty=${encodeURIComponent(difficulty)}&size=${size}`;

  fetch(url, { signal: abortController.signal })
    .then(async (response) => {
      if (!response.ok) {
        if (response.status === 429) {
          onError("Slow down! Too many puzzles. Try again in a minute.");
        } else {
          onError(`Server error: ${response.status}`);
        }
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

export async function recluePuzzle(
  puzzle: PuzzleData,
  difficulty: string
): Promise<{ clues: PuzzleData["clues"]; cost_cents: number }> {
  const response = await fetch("/api/reclue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ puzzle, difficulty }),
  });
  if (!response.ok) {
    if (response.status === 429) {
      throw new Error("Slow down! Try upgrading clues again in a minute.");
    }
    throw new Error(`Reclue failed: ${response.status}`);
  }
  return response.json();
}
