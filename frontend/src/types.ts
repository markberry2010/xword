export interface PuzzleData {
  size: number;
  grid: string[]; // e.g. ["HELLO", "A.RLD"] where . = black
  clues: Record<
    string,
    {
      word: string;
      clue: string;
      difficulty: string;
      alternatives: string[];
    }
  >;
  metadata: {
    difficulty: string;
    theme: string | null;
    generated_at: string;
    version: string;
  };
}

export interface Cell {
  row: number;
  col: number;
  isBlack: boolean;
  number: number | null;
  solution: string;
  userLetter: string;
  state: "empty" | "filled" | "checked-correct" | "checked-wrong" | "revealed";
}

export type Direction = "across" | "down";

export interface CursorState {
  row: number;
  col: number;
  direction: Direction;
}

export interface ClueInfo {
  id: string; // "1A", "3D"
  number: number;
  direction: Direction;
  clue: string;
  word: string;
  cells: [number, number][];
}

export interface ProgressEvent {
  stage: string;
  message: string;
  pct: number;
}
