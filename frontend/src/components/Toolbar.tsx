interface Props {
  timer: string;
  onCheck: () => void;
  onReveal: () => void;
  onReset: () => void;
}

export function Toolbar({ timer, onCheck, onReveal, onReset }: Props) {
  return (
    <div className="toolbar">
      <span className="timer">{timer}</span>
      <div className="toolbar-buttons">
        <button onClick={onCheck}>Check</button>
        <button onClick={onReveal}>Reveal</button>
        <button onClick={onReset}>Reset</button>
      </div>
    </div>
  );
}
