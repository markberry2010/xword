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

  const activeCells = new Set(
    activeClue?.cells.map(([r, c]) => `${r},${c}`) || []
  );

  return (
    <div
      className="crossword-grid"
      tabIndex={0}
      onKeyDown={onKeyDown}
      style={{
        gridTemplateColumns: `repeat(${size}, 1fr)`,
        gridTemplateRows: `repeat(${size}, 1fr)`,
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
            onClick={() => onCellClick(cell.row, cell.col)}
          >
            {cell.number && <span className="cell-number">{cell.number}</span>}
            {!cell.isBlack && (
              <span className="cell-letter">{cell.userLetter}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
