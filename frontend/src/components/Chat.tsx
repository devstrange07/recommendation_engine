import { useEffect, useRef, useState } from "react";
import {
  ChatMessage,
  DebugTrace,
  ProductCard,
  postChat,
} from "../api";
import TiltWrap from "../hooks/useTilt";

type Props = {
  sessionId: string;
  country: string;
  tenantId: string;
  catalogTitle: string;
  messages: ChatMessage[];
  cardsByTurn: Record<number, ProductCard[]>;
  initialPrompt?: string;
  onInitialPromptConsumed?: () => void;
  onCountryChange: (c: string) => void;
  onMessagesChange: (patch: {
    messages: ChatMessage[];
    cardsByTurn: Record<number, ProductCard[]>;
    lastDebug: DebugTrace | null;
  }) => void;
  onDebug: (d: DebugTrace | null) => void;
  onNewChat: () => void;
  onToggleDebug: () => void;
  debugOpen: boolean;
  onAddProducts: () => void;
};

export default function Chat({
  sessionId,
  country,
  tenantId,
  catalogTitle,
  messages,
  cardsByTurn,
  initialPrompt,
  onInitialPromptConsumed,
  onCountryChange,
  onMessagesChange,
  onDebug,
  onNewChat,
  onToggleDebug,
  debugOpen,
  onAddProducts,
}: Props) {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const composerInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  useEffect(() => {
    if (!busy) {
      composerInputRef.current?.focus();
    }
  }, [busy]);

  useEffect(() => {
    if (initialPrompt) {
      setInput(initialPrompt);
      onInitialPromptConsumed?.();
    }
  }, [initialPrompt, onInitialPromptConsumed]);

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    const next = [...messages, { role: "user" as const, content: text }];
    onMessagesChange({ messages: next, cardsByTurn, lastDebug: null });
    setInput("");
    setBusy(true);
    try {
      const res = await postChat(sessionId, country, next, tenantId, catalogTitle);
      const withAssistant = [...next, { role: "assistant" as const, content: res.reply }];
      const nextCards = { ...cardsByTurn, [withAssistant.length - 1]: res.product_cards };
      onMessagesChange({
        messages: withAssistant,
        cardsByTurn: nextCards,
        lastDebug: res.debug,
      });
      onDebug(res.debug);
    } catch (e) {
      const errMsg = `Error: ${e instanceof Error ? e.message : String(e)}`;
      onMessagesChange({
        messages: [...next, { role: "assistant", content: errMsg }],
        cardsByTurn,
        lastDebug: null,
      });
    } finally {
      setBusy(false);
      requestAnimationFrame(() => composerInputRef.current?.focus());
    }
  }

  return (
    <div className="chat chat--compact">
      <header className="bento-tile__header chat-header-compact">
        <h2 className="bento-tile__title">
          Chat ({catalogTitle})
        </h2>
        <div className="chat-header-actions">
          <label className="chat-country">
            Country{" "}
            <select value={country} onChange={(e) => onCountryChange(e.target.value)}>
              <option value="IN">IN (INR)</option>
              <option value="US">US (USD)</option>
              <option value="GB">GB (GBP)</option>
            </select>
          </label>
          <button type="button" className="ghost" onClick={onAddProducts}>
            Add products
          </button>
          <button type="button" className="ghost" onClick={onNewChat}>
            New chat
          </button>
          <button
            type="button"
            className={debugOpen ? "active" : "ghost"}
            onClick={onToggleDebug}
          >
            Retrieval
          </button>
        </div>
      </header>
      <div className="messages messages--compact">
        {messages.length === 0 && (
          <div className="empty">
            <p>
              Try: “I run a small salon and drowning in appointment calls” — then narrow with a
              budget or billing preference.
            </p>
            <button type="button" className="primary" onClick={onAddProducts}>
              Add products
            </button>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} style={{ animationDelay: `${i * 40}ms` }}>
            <div className={`bubble ${m.role}`}>{m.content}</div>
            {cardsByTurn[i]?.length ? (
              <div className="cards-row">
                {cardsByTurn[i].map((c) => (
                  <TiltWrap key={c.id}>
                    <div className="product-card product-card--chip">
                      <strong>{c.title}</strong>
                      <div className="price">{c.price_display}</div>
                    </div>
                  </TiltWrap>
                ))}
              </div>
            ) : null}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
      {busy && <div className="typing">Thinking…</div>}
      <div className="composer composer--compact">
        <input
          ref={composerInputRef}
          value={input}
          placeholder="Message…"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          disabled={busy}
        />
        <button className="primary" onClick={send} disabled={busy || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  );
}
