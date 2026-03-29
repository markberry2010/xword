import { useState, useCallback, useMemo } from "react";
import type { Cell, PuzzleData, ClueInfo, Direction } from "../types";

function buildCells(puzzle: PuzzleData): Cell[][] {
  const { size, grid } = puzzle;

  // Figure out which cells start clues by scanning the grid
  const isBlack = (r: number, c: number) =>
    r < 0 || r >= size || c < 0 || c >= size || grid[r][c] === ".";

  const cellNumbers: number[][] = Array.from({ length: size }, () =>
    Array(size).fill(0)
  );
  let num = 1;
  for (let r = 0; r < size; r++) {
    for (let c = 0; c < size; c++) {
      if (isBlack(r, c)) continue;
      const startsAcross = (c === 0 || isBlack(r, c - 1)) && !isBlack(r, c + 1);
      const startsDown = (r === 0 || isBlack(r - 1, c)) && !isBlack(r + 1, c);
      if (startsAcross || startsDown) {
        cellNumbers[r][c] = num++;
      }
    }
  }

  return Array.from({ length: size }, (_, r) =>
    Array.from({ length: size }, (_, c) => ({
      row: r,
      col: c,
      isBlack: grid[r][c] === ".",
      number: cellNumbers[r][c] || null,
      solution: grid[r][c] === "." ? "" : grid[r][c],
      userLetter: "",
      state: "empty" as const,
    }))
  );
}

function buildClues(puzzle: PuzzleData, cells: Cell[][]): ClueInfo[] {
  const { size, grid, clues } = puzzle;
  const result: ClueInfo[] = [];

  const isBlack = (r: number, c: number) =>
    r < 0 || r >= size || c < 0 || c >= size || grid[r][c] === ".";

  for (const [id, clueData] of Object.entries(clues)) {
    const num = parseInt(id.slice(0, -1));
    const direction: Direction = id.endsWith("A") ? "across" : "down";

    // Find the cell with this number
    let startR = -1,
      startC = -1;
    for (let r = 0; r < size && startR === -1; r++) {
      for (let c = 0; c < size; c++) {
        if (cells[r][c].number === num) {
          startR = r;
          startC = c;
          break;
        }
      }
    }

    if (startR === -1) continue;

    // Collect cells for this clue
    const clueCells: [number, number][] = [];
    if (direction === "across") {
      for (let c = startC; c < size && !isBlack(startR, c); c++) {
        clueCells.push([startR, c]);
      }
    } else {
      for (let r = startR; r < size && !isBlack(r, startC); r++) {
        clueCells.push([r, startC]);
      }
    }

    result.push({
      id,
      number: num,
      direction,
      clue: clueData.clue,
      word: clueData.word,
      cells: clueCells,
    });
  }

  // Sort: across first, then down, by number
  result.sort((a, b) => {
    if (a.direction !== b.direction)
      return a.direction === "across" ? -1 : 1;
    return a.number - b.number;
  });

  return result;
}

export function usePuzzle(puzzle: PuzzleData) {
  const [cells, setCells] = useState(() => buildCells(puzzle));
  const clueInfos = useMemo(() => buildClues(puzzle, cells), [puzzle]);

  const setLetter = useCallback(
    (row: number, col: number, letter: string) => {
      setCells((prev) => {
        const next = prev.map((r) => r.map((c) => ({ ...c })));
        const cell = next[row][col];
        if (cell.isBlack) return prev;
        cell.userLetter = letter.toUpperCase();
        cell.state = letter ? "filled" : "empty";
        return next;
      });
    },
    []
  );

  const checkAll = useCallback(() => {
    setCells((prev) =>
      prev.map((row) =>
        row.map((cell) => {
          if (cell.isBlack || cell.state === "revealed") return cell;
          if (!cell.userLetter) return cell;
          return {
            ...cell,
            state:
              cell.userLetter === cell.solution
                ? "checked-correct"
                : "checked-wrong",
          };
        })
      )
    );
  }, []);

  const revealAll = useCallback(() => {
    setCells((prev) =>
      prev.map((row) =>
        row.map((cell) => {
          if (cell.isBlack) return cell;
          return {
            ...cell,
            userLetter: cell.solution,
            state: "revealed",
          };
        })
      )
    );
  }, []);

  const reset = useCallback(() => {
    setCells((prev) =>
      prev.map((row) =>
        row.map((cell) => {
          if (cell.isBlack) return cell;
          return { ...cell, userLetter: "", state: "empty" as const };
        })
      )
    );
  }, []);

  const isComplete = useMemo(() => {
    return cells.every((row) =>
      row.every(
        (cell) => cell.isBlack || cell.userLetter === cell.solution
      )
    );
  }, [cells]);

  const getClueForCell = useCallback(
    (row: number, col: number, direction: Direction): ClueInfo | null => {
      return (
        clueInfos.find(
          (c) =>
            c.direction === direction &&
            c.cells.some(([r, cc]) => r === row && cc === col)
        ) || null
      );
    },
    [clueInfos]
  );

  return {
    cells,
    clueInfos,
    setLetter,
    checkAll,
    revealAll,
    reset,
    isComplete,
    getClueForCell,
  };
}
