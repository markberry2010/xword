import { useEffect, useRef, useState } from "react";
import type { PuzzleData } from "../types";
import { recluePuzzle } from "../api";
import { usePuzzle } from "../hooks/usePuzzle";
import { useNavigation } from "../hooks/useNavigation";
import { useTimer } from "../hooks/useTimer";
import { CrosswordGrid } from "./CrosswordGrid";
import { ClueList } from "./ClueList";
import { Toolbar } from "./Toolbar";

interface Props {
  puzzle: PuzzleData;
  costCents: number | null;
  onNewPuzzle: () => void;
  onPuzzleUpdate: (puzzle: PuzzleData, costCents: number | null) => void;
}

export function PlayPage({ puzzle, costCents, onNewPuzzle, onPuzzleUpdate }: Props) {
  const { cells, clueInfos, setLetter, checkAll, revealAll, reset, isComplete } =
    usePuzzle(puzzle);
  const { cursor, activeClue, handleKeyDown, clickCell, jumpToClue } =
    useNavigation(cells, clueInfos, setLetter);
  const timer = useTimer();
  const gridRef = useRef<HTMLDivElement>(null);
  const [finished, setFinished] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [recluing, setRecluing] = useState(false);
  const [hasReclued, setHasReclued] = useState(false);
  const hasStarted = useRef(false);

  const wrappedKeyDown = (e: React.KeyboardEvent) => {
    if (!hasStarted.current && /^[a-zA-Z]$/.test(e.key)) {
      hasStarted.current = true;
      timer.start();
    }
    handleKeyDown(e);
  };

  useEffect(() => {
    gridRef.current?.querySelector<HTMLDivElement>(".crossword-grid")?.focus();
  }, []);

  useEffect(() => {
    if (isComplete && hasStarted.current && !finished) {
      timer.stop();
      setFinished(true);
      setShowModal(true);
    }
  }, [isComplete, timer, finished]);

  const handleReveal = () => {
    revealAll();
    timer.stop();
    setFinished(true);
  };

  const handleReset = () => {
    reset();
    timer.reset();
    hasStarted.current = false;
    setFinished(false);
    setShowModal(false);
  };

  const handleReclue = async () => {
    setRecluing(true);
    try {
      const result = await recluePuzzle(puzzle, puzzle.metadata.difficulty);
      const updated = { ...puzzle, clues: result.clues };
      const newCost = (costCents ?? 0) + result.cost_cents;
      onPuzzleUpdate(updated, newCost);
      setHasReclued(true);
    } catch {
      // silently fail
    } finally {
      setRecluing(false);
    }
  };

  // Joel makes ~$100k/year, ~$274/day, ~1 puzzle/day
  const joelDailyCost = 274;
  const costMultiplier =
    costCents && costCents > 0
      ? Math.round(joelDailyCost / (costCents / 100))
      : null;

  const costBlock = costCents !== null && (
    <p className="cost-info">
      This puzzle cost {costCents.toFixed(1)} cents to generate.
      {costMultiplier && (
        <>
          {" "}That's {costMultiplier.toLocaleString()}x cheaper than Joel.
          And it doesn't need health insurance.
        </>
      )}
    </p>
  );

  return (
    <div className="play-page">
      <header className="play-header">
        <h1>Project Unemploy Joel</h1>
        <p className="subtitle">Mini Crossword</p>
      </header>

      <Toolbar
        timer={timer.formatted}
        onCheck={checkAll}
        onReveal={handleReveal}
        onReset={handleReset}
      />

      <div className="play-layout" ref={gridRef}>
        <CrosswordGrid
          cells={cells}
          cursor={cursor}
          activeClue={activeClue}
          onCellClick={clickCell}
          onKeyDown={wrappedKeyDown}
        />
        <div className="clue-panel">
          <ClueList
            clues={clueInfos}
            activeClue={activeClue}
            onClueClick={jumpToClue}
          />
          {!hasReclued && (
            <button
              className="reclue-btn"
              onClick={handleReclue}
              disabled={recluing}
            >
              {recluing ? "Thinking harder..." : "Upgrade clues with Opus"}
            </button>
          )}
          {hasReclued && (
            <p className="reclue-done">Clues upgraded with Opus</p>
          )}
        </div>
      </div>

      {showModal && (
        <div className="modal-backdrop" onClick={() => setShowModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-diamond" />
            <h2>Brilliant</h2>
            <p className="modal-time">{timer.formatted}</p>
            {costBlock}
            <button className="new-puzzle-btn" onClick={onNewPuzzle}>
              Generate New Puzzle
            </button>
          </div>
        </div>
      )}

      {finished && !showModal && (
        <div className="finish-section">
          <h2>{isComplete ? "Solved" : "Revealed"}</h2>
          {isComplete && <p className="finish-time">{timer.formatted}</p>}
          {costBlock}
          <button className="new-puzzle-btn" onClick={onNewPuzzle}>
            Generate New Puzzle
          </button>
        </div>
      )}
    </div>
  );
}
