import { useState } from "react";
import type { PuzzleData } from "./types";
import { GeneratePage } from "./components/GeneratePage";
import { PlayPage } from "./components/PlayPage";
import "./styles/global.css";

export default function App() {
  const [puzzle, setPuzzle] = useState<PuzzleData | null>(null);
  const [costCents, setCostCents] = useState<number | null>(null);

  if (puzzle) {
    return (
      <PlayPage
        puzzle={puzzle}
        costCents={costCents}
        onNewPuzzle={() => {
          setPuzzle(null);
          setCostCents(null);
        }}
        onPuzzleUpdate={(p, cost) => {
          setPuzzle(p);
          setCostCents(cost);
        }}
      />
    );
  }

  return (
    <GeneratePage
      onPuzzleReady={(p, cost) => {
        setPuzzle(p);
        setCostCents(cost);
      }}
    />
  );
}
