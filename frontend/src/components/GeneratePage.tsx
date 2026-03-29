import { useState } from "react";
import type { PuzzleData, ProgressEvent } from "../types";
import { generatePuzzle } from "../api";

interface Props {
  onPuzzleReady: (puzzle: PuzzleData, costCents: number | null) => void;
}

const SIZES = [
  { value: 5, label: "5 x 5", desc: "Mini" },
  { value: 7, label: "7 x 7", desc: "Midi" },
];

export function GeneratePage({ onPuzzleReady }: Props) {
  const [difficulty, setDifficulty] = useState("easy");
  const [size, setSize] = useState(5);
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState<ProgressEvent | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = () => {
    setGenerating(true);
    setError(null);
    setProgress({ stage: "starting", message: "Starting...", pct: 0 });

    generatePuzzle(
      difficulty,
      size,
      (evt) => setProgress(evt),
      (puzzle, costCents) => {
        setGenerating(false);
        onPuzzleReady(puzzle, costCents);
      },
      (msg) => {
        setGenerating(false);
        setError(msg);
      }
    );
  };

  return (
    <div className="generate-page">
      <div className="generate-card">
        <h1>Project Unemploy Joel</h1>
        <p className="tagline">AI-generated crosswords</p>

        <div className="picker-label">Size</div>
        <div className="size-picker">
          {SIZES.map((s) => (
            <button
              key={s.value}
              className={`size-btn ${size === s.value ? "selected" : ""}`}
              onClick={() => setSize(s.value)}
              disabled={generating}
            >
              <span className="size-label">{s.label}</span>
              <span className="size-desc">{s.desc}</span>
            </button>
          ))}
        </div>

        <div className="picker-label">Clue difficulty</div>
        <div className="difficulty-picker">
          {["easy", "medium", "hard"].map((d) => (
            <button
              key={d}
              className={`diff-btn ${difficulty === d ? "selected" : ""}`}
              onClick={() => setDifficulty(d)}
              disabled={generating}
            >
              {d.charAt(0).toUpperCase() + d.slice(1)}
            </button>
          ))}
        </div>

        {!generating ? (
          <button className="generate-btn" onClick={handleGenerate}>
            Generate Puzzle
          </button>
        ) : (
          <div className="progress-section">
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${progress?.pct || 0}%` }}
              />
            </div>
            <p className="progress-message">{progress?.message || "..."}</p>
          </div>
        )}

        {error && <p className="error-message">{error}</p>}
      </div>
      <p className="footer-note">made with love from a fellow blaisdell 132 resident</p>
    </div>
  );
}
