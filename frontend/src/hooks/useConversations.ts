import { useCallback, useEffect, useMemo, useState } from "react";
import { ChatMessage, DebugTrace, ProductCard } from "../api";

const STORAGE_KEY = "prism-conversations-v1";

export type Conversation = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: ChatMessage[];
  cardsByTurn: Record<number, ProductCard[]>;
  lastDebug: DebugTrace | null;
};

type Store = {
  conversations: Conversation[];
  activeId: string;
};

function newId(): string {
  return `c_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
}

export function createEmptyConversation(): Conversation {
  const now = Date.now();
  return {
    id: newId(),
    title: "New chat",
    createdAt: now,
    updatedAt: now,
    messages: [],
    cardsByTurn: {},
    lastDebug: null,
  };
}

function loadStore(): Store {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Store;
      if (parsed.conversations?.length && parsed.activeId) {
        return parsed;
      }
    }
  } catch {
    /* ignore corrupt storage */
  }
  const first = createEmptyConversation();
  return { conversations: [first], activeId: first.id };
}

function titleFromMessages(messages: ChatMessage[], current: string): string {
  if (current !== "New chat") return current;
  const firstUser = messages.find((m) => m.role === "user");
  if (!firstUser) return current;
  const t = firstUser.content.trim().replace(/\s+/g, " ");
  return t.length > 40 ? `${t.slice(0, 40)}…` : t || current;
}

export function useConversations() {
  const [store, setStore] = useState<Store>(() => loadStore());

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  }, [store]);

  const active = useMemo(
    () => store.conversations.find((c) => c.id === store.activeId) ?? store.conversations[0],
    [store]
  );

  const create = useCallback(() => {
    const conv = createEmptyConversation();
    setStore((prev) => ({
      conversations: [conv, ...prev.conversations],
      activeId: conv.id,
    }));
    return conv.id;
  }, []);

  const select = useCallback((id: string) => {
    setStore((prev) =>
      prev.conversations.some((c) => c.id === id) ? { ...prev, activeId: id } : prev
    );
  }, []);

  const updateActive = useCallback(
    (patch: Partial<Pick<Conversation, "messages" | "cardsByTurn" | "lastDebug" | "title">>) => {
      setStore((prev) => {
        const idx = prev.conversations.findIndex((c) => c.id === prev.activeId);
        if (idx < 0) return prev;
        const cur = prev.conversations[idx];
        const messages = patch.messages ?? cur.messages;
        const next: Conversation = {
          ...cur,
          ...patch,
          messages,
          title: patch.title ?? titleFromMessages(messages, cur.title),
          updatedAt: Date.now(),
        };
        const conversations = [...prev.conversations];
        conversations[idx] = next;
        return { ...prev, conversations };
      });
    },
    []
  );

  const remove = useCallback((id: string) => {
    setStore((prev) => {
      const conversations = prev.conversations.filter((c) => c.id !== id);
      if (conversations.length === 0) {
        const fresh = createEmptyConversation();
        return { conversations: [fresh], activeId: fresh.id };
      }
      const activeId =
        prev.activeId === id ? conversations[0].id : prev.activeId;
      return { conversations, activeId };
    });
  }, []);

  const rename = useCallback((id: string, title: string) => {
    setStore((prev) => ({
      ...prev,
      conversations: prev.conversations.map((c) =>
        c.id === id ? { ...c, title: title.trim() || c.title, updatedAt: Date.now() } : c
      ),
    }));
  }, []);

  return {
    conversations: store.conversations,
    activeId: store.activeId,
    active,
    create,
    select,
    updateActive,
    remove,
    rename,
  };
}
