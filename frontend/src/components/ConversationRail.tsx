import type { Conversation } from "../hooks/useConversations";

type Props = {
  conversations: Conversation[];
  activeId: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onRemove: (id: string) => void;
};

function relativeTime(ts: number): string {
  const sec = Math.round((Date.now() - ts) / 1000);
  if (sec < 60) return "just now";
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  return `${day}d ago`;
}

export default function ConversationRail({
  conversations,
  activeId,
  onSelect,
  onCreate,
  onRemove,
}: Props) {
  return (
    <aside className="bento-tile bento-tile--rail conversation-rail">
      <header className="conversation-rail__header">
        <button type="button" className="primary conversation-rail__new" onClick={onCreate}>
          New chat
        </button>
      </header>
      <ul className="conversation-rail__list">
        {conversations.map((c) => (
          <li key={c.id}>
            <button
              type="button"
              className={`conversation-rail__item ${c.id === activeId ? "active" : ""}`}
              onClick={() => onSelect(c.id)}
            >
              <span className="conversation-rail__title">{c.title}</span>
              <span className="conversation-rail__meta">{relativeTime(c.updatedAt)}</span>
            </button>
            <button
              type="button"
              className="ghost conversation-rail__delete"
              title="Delete conversation"
              aria-label={`Delete ${c.title}`}
              onClick={(e) => {
                e.stopPropagation();
                onRemove(c.id);
              }}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
