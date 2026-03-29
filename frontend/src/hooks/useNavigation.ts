import { useState, useCallback, useRef, useEffect } from "react";
import type { Cell, CursorState, ClueInfo } from "../types";

export function useNavigation(
  cells: Cell[][],
  clueInfos: ClueInfo[],
  setLetter: (row: number, col: number, letter: string) => void
) {
  const size = cells.length;
  const cellsRef = useRef(cells);
  useEffect(() => {
    cellsRef.current = cells;
  }, [cells]);

  const [cursor, setCursor] = useState<CursorState>(() => {
    for (let r = 0; r < size; r++) {
      for (let c = 0; c < size; c++) {
        if (!cells[r][c].isBlack) return { row: r, col: c, direction: "across" };
      }
    }
    return { row: 0, col: 0, direction: "across" };
  });

  const isBlack = useCallback(
    (r: number, c: number) =>
      r < 0 || r >= size || c < 0 || c >= size || cellsRef.current[r][c].isBlack,
    [size]
  );

  const jumpToClue = useCallback(
    (clue: ClueInfo) => {
      if (clue.cells.length > 0) {
        const firstEmpty = clue.cells.find(
          ([r, c]) => !cellsRef.current[r][c].userLetter
        );
        const [r, c] = firstEmpty || clue.cells[0];
        setCursor({ row: r, col: c, direction: clue.direction });
      }
    },
    []
  );

  const clickCell = useCallback(
    (row: number, col: number) => {
      if (isBlack(row, col)) return;
      setCursor((prev) => {
        if (prev.row === row && prev.col === col) {
          return { row, col, direction: prev.direction === "across" ? "down" : "across" };
        }
        return { row, col, direction: prev.direction };
      });
    },
    [isBlack]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const key = e.key;
      e.preventDefault();

      if (key === "ArrowUp" || key === "ArrowDown") {
        setCursor((prev) => {
          // First press switches to down mode; already in down mode moves
          if (prev.direction !== "down") {
            return { ...prev, direction: "down" };
          }
          const dr = key === "ArrowUp" ? -1 : 1;
          let r = prev.row + dr;
          while (r >= 0 && r < size && isBlack(r, prev.col)) r += dr;
          if (r >= 0 && r < size && !isBlack(r, prev.col)) {
            return { ...prev, row: r };
          }
          return prev;
        });
      } else if (key === "ArrowLeft" || key === "ArrowRight") {
        setCursor((prev) => {
          if (prev.direction !== "across") {
            return { ...prev, direction: "across" };
          }
          const dc = key === "ArrowLeft" ? -1 : 1;
          let c = prev.col + dc;
          while (c >= 0 && c < size && isBlack(prev.row, c)) c += dc;
          if (c >= 0 && c < size && !isBlack(prev.row, c)) {
            return { ...prev, col: c };
          }
          return prev;
        });
      } else if (key === "Tab") {
        setCursor((prev) => {
          const currentClue = clueInfos.find(
            (c) =>
              c.direction === prev.direction &&
              c.cells.some(([r, cc]) => r === prev.row && cc === prev.col)
          );
          if (!currentClue) return prev;
          const idx = clueInfos.indexOf(currentClue);
          const next = clueInfos[(idx + 1) % clueInfos.length];
          if (next && next.cells.length > 0) {
            const firstEmpty = next.cells.find(
              ([r, c]) => !cellsRef.current[r][c].userLetter
            );
            const [r, c] = firstEmpty || next.cells[0];
            return { row: r, col: c, direction: next.direction };
          }
          return prev;
        });
      } else if (key === " ") {
        setCursor((prev) => ({
          ...prev,
          direction: prev.direction === "across" ? "down" : "across",
        }));
      } else if (key === "Backspace") {
        setCursor((prev) => {
          const cell = cellsRef.current[prev.row][prev.col];
          if (cell.userLetter) {
            setLetter(prev.row, prev.col, "");
            return prev;
          }
          // Move backward
          const dr = prev.direction === "down" ? -1 : 0;
          const dc = prev.direction === "across" ? -1 : 0;
          const r = prev.row + dr;
          const c = prev.col + dc;
          if (r >= 0 && r < size && c >= 0 && c < size && !isBlack(r, c)) {
            setLetter(r, c, "");
            return { ...prev, row: r, col: c };
          }
          return prev;
        });
      } else if (/^[a-zA-Z]$/.test(key)) {
        setCursor((prev) => {
          setLetter(prev.row, prev.col, key.toUpperCase());
          // Advance
          const dr = prev.direction === "down" ? 1 : 0;
          const dc = prev.direction === "across" ? 1 : 0;
          const r = prev.row + dr;
          const c = prev.col + dc;
          if (r >= 0 && r < size && c >= 0 && c < size && !isBlack(r, c)) {
            return { ...prev, row: r, col: c };
          }
          return prev;
        });
      }
    },
    [size, isBlack, clueInfos, setLetter]
  );

  const activeClue =
    clueInfos.find(
      (c) =>
        c.direction === cursor.direction &&
        c.cells.some(([r, cc]) => r === cursor.row && cc === cursor.col)
    ) || null;

  return {
    cursor,
    activeClue,
    handleKeyDown,
    clickCell,
    jumpToClue,
  };
}
