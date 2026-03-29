import type { ClueInfo } from "../types";

interface Props {
  clues: ClueInfo[];
  activeClue: ClueInfo | null;
  onClueClick: (clue: ClueInfo) => void;
}

export function ClueList({ clues, activeClue, onClueClick }: Props) {
  const across = clues.filter((c) => c.direction === "across");
  const down = clues.filter((c) => c.direction === "down");

  return (
    <div className="clue-list">
      <div className="clue-section">
        <h3>Across</h3>
        {across.map((clue) => (
          <div
            key={clue.id}
            className={`clue-item ${activeClue?.id === clue.id ? "active" : ""}`}
            onClick={() => onClueClick(clue)}
          >
            <span className="clue-number">{clue.number}</span>
            <span className="clue-text">{clue.clue}</span>
          </div>
        ))}
      </div>
      <div className="clue-section">
        <h3>Down</h3>
        {down.map((clue) => (
          <div
            key={clue.id}
            className={`clue-item ${activeClue?.id === clue.id ? "active" : ""}`}
            onClick={() => onClueClick(clue)}
          >
            <span className="clue-number">{clue.number}</span>
            <span className="clue-text">{clue.clue}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
