const tools = ['+', '/', '↗', '↕', '⬚', '✎', '◯', '≡', 'T', '👁'];

export function SideToolbar() {
  return (
    <aside className="side-toolbar" aria-label="Drawing tools">
      {tools.map((item) => (
        <button key={item} type="button" className="tool-btn">
          {item}
        </button>
      ))}
    </aside>
  );
}
