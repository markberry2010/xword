import { useRef, useEffect } from "react";
import type { Cell, CursorState, ClueInfo } from "../types";
import "../styles/grid.css";

interface Props {
  cells: Cell[][];
  cursor: CursorState;
  activeClue: ClueInfo | null;
  onCellClick: (row: number, col: number) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
}

export function CrosswordGrid({
  cells,
  cursor,
  activeClue,
  onCellClick,
  onKeyDown,
}: Props) {
  const size = cells.length;
  const inputRef = useRef<HTMLInputElement>(null);

  const activeCells = new Set(
    activeClue?.cells.map(([r, c]) => `${r},${c}`) || []
  );

  // Keep hidden input focused for mobile keyboard
  useEffect(() => {
    inputRef.current?.focus();
  }, [cursor]);

  const handleInput = (e: React.FormEvent<HTMLInputElement>) => {
    const value = e.currentTarget.value;
    if (value) {
      // Simulate a keydown event for the last character typed
      const letter = value.slice(-1);
      if (/^[a-zA-Z]$/.test(letter)) {
        const synth = new KeyboardEvent("keydown", {
          key: letter,
          bubbles: true,
        });
        onKeyDown(synth as unknown as React.KeyboardEvent);
      }
    }
    // Always clear the input so the next character is fresh
    e.currentTarget.value = "";
  };

  const handleHiddenKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (["Backspace", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Tab", " "].includes(e.key)) {
      onKeyDown(e);
    }
  };

  // Scale grid dimensions and font size based on puzzle size
  const cellPx = size <= 5 ? 64 : size <= 7 ? 50 : size <= 9 ? 42 : 32;
  const gridPx = cellPx * size + 6; // +6 for border
  const letterSize = size <= 5 ? 24 : size <= 7 ? 20 : size <= 9 ? 16 : 13;
  const numberSize = size <= 7 ? 9 : 7;

  return (
    <div className="crossword-grid-wrapper">
      <input
        ref={inputRef}
        className="grid-hidden-input"
        type="text"
        autoCapitalize="characters"
        autoComplete="off"
        autoCorrect="off"
        spellCheck={false}
        enterKeyHint="next"
        onInput={handleInput}
        onKeyDown={handleHiddenKeyDown}
      />
      <div
        className="crossword-grid"
        tabIndex={0}
        onKeyDown={onKeyDown}
        onClick={() => inputRef.current?.focus()}
        style={{
          gridTemplateColumns: `repeat(${size}, 1fr)`,
          gridTemplateRows: `repeat(${size}, 1fr)`,
          width: `${gridPx}px`,
          height: `${gridPx}px`,
          // Pass sizing to cells via CSS custom properties
          ["--cell-letter-size" as string]: `${letterSize}px`,
          ["--cell-number-size" as string]: `${numberSize}px`,
        }}
      >
        {cells.flat().map((cell) => {
          const isActive = cursor.row === cell.row && cursor.col === cell.col;
          const isInActiveWord = activeCells.has(`${cell.row},${cell.col}`);

          let className = "grid-cell";
          if (cell.isBlack) className += " black";
          else if (isActive) className += " active";
          else if (isInActiveWord) className += " in-word";

          if (cell.state === "checked-correct") className += " correct";
          if (cell.state === "checked-wrong") className += " wrong";
          if (cell.state === "revealed") className += " revealed";

          return (
            <div
              key={`${cell.row}-${cell.col}`}
              className={className}
              onClick={() => {
                onCellClick(cell.row, cell.col);
                inputRef.current?.focus();
              }}
            >
              {cell.number && <span className="cell-number">{cell.number}</span>}
              {!cell.isBlack && (
                <span className="cell-letter">{cell.userLetter}</span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
