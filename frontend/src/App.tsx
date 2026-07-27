import { useEffect, useState } from "react";
import Chat from "./components/Chat";
import DebugPanel from "./components/DebugPanel";
import ReviewQueue from "./components/ReviewQueue";
import Catalog from "./components/Catalog";
import Onboarding, {
  clearOnboarding,
  isOnboardingDone,
} from "./components/Onboarding";
import ConversationRail from "./components/ConversationRail";
import BentoGrid from "./components/BentoGrid";
import BentoTile from "./components/BentoTile";
import { useConversations } from "./hooks/useConversations";
import { DEMO_CATALOG_ID, useCatalogs } from "./hooks/useCatalogs";
import { DebugTrace, ProductCard } from "./api";

type Page = "chat" | "review" | "catalog";

const DEBUG_KEY = "prism-debug-open";

function latestShortlist(cardsByTurn: Record<number, ProductCard[]> | undefined): ProductCard[] {
  if (!cardsByTurn) return [];
  const keys = Object.keys(cardsByTurn)
    .map(Number)
    .filter((k) => cardsByTurn[k]?.length)
    .sort((a, b) => b - a);
  return keys.length ? cardsByTurn[keys[0]] : [];
}

export default function App() {
  const [page, setPage] = useState<Page>("chat");
  const [country, setCountry] = useState("IN");
  const [chatPrompt, setChatPrompt] = useState("");
  const [debug, setDebug] = useState<DebugTrace | null>(null);
  const [debugOpen, setDebugOpen] = useState(() => {
    try {
      const stored = sessionStorage.getItem(DEBUG_KEY);
      if (stored === null) return true;
      return stored === "1";
    } catch {
      return true;
    }
  });
  const [onboarded, setOnboarded] = useState(() => isOnboardingDone());
  const [showTour, setShowTour] = useState(() => !isOnboardingDone());

  const {
    conversations,
    activeId,
    active,
    create,
    select,
    updateActive,
    remove,
  } = useConversations();

  const {
    catalogs,
    activeId: catalogId,
    active: activeCatalog,
    create: createCatalog,
    select: selectCatalog,
  } = useCatalogs();

  useEffect(() => {
    try {
      sessionStorage.setItem(DEBUG_KEY, debugOpen ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [debugOpen]);

  useEffect(() => {
    setDebug(active?.lastDebug ?? null);
  }, [activeId, active?.lastDebug]);

  function completeOnboarding() {
    setOnboarded(true);
    setShowTour(false);
  }

  function replayTour() {
    clearOnboarding();
    setOnboarded(false);
    setShowTour(true);
  }

  function ensureUserCatalog(): string {
    if (catalogId !== DEMO_CATALOG_ID) return catalogId;
    const existing = catalogs.find((c) => c.id !== DEMO_CATALOG_ID);
    if (existing) {
      selectCatalog(existing.id);
      return existing.id;
    }
    return createCatalog("My catalog");
  }

  function tryInChat(productName: string) {
    ensureUserCatalog();
    setChatPrompt(`I'm looking for ${productName}. What plans do you offer?`);
    create();
    setPage("chat");
  }

  function goAddProducts() {
    ensureUserCatalog();
    setPage("catalog");
  }

  function onNewCatalog() {
    const name = window.prompt("Catalog name", "New catalog");
    if (name === null) return;
    createCatalog(name.trim() || "New catalog");
    setPage("catalog");
  }

  function toggleDebug() {
    setDebugOpen((v) => !v);
  }

  const catalogTitle = activeCatalog?.title ?? "Demo catalog";
  const shortlist = latestShortlist(active?.cardsByTurn);

  return (
    <>
      {showTour && <Onboarding onComplete={completeOnboarding} />}
      <div className={`app-shell page-${page} ${showTour ? "dimmed" : ""}`}>
        <header className="topbar">
          <div className="brand">
            <h1>Prism</h1>
            <p className="brand-tagline">Talk to your HybridShelf</p>
          </div>
          <label className="catalog-mode">
            Catalog{" "}
            <select
              value={catalogId}
              onChange={(e) => selectCatalog(e.target.value)}
            >
              {catalogs.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
            <button type="button" className="ghost catalog-mode-link" onClick={onNewCatalog}>
              New catalog
            </button>
            {catalogId === DEMO_CATALOG_ID && (
              <button type="button" className="ghost catalog-mode-link" onClick={goAddProducts}>
                Add products
              </button>
            )}
          </label>
          <nav>
            <button className={page === "chat" ? "active" : ""} onClick={() => setPage("chat")}>
              Chat
            </button>
            <button
              className={page === "catalog" ? "active" : ""}
              onClick={() => setPage("catalog")}
            >
              Catalog
            </button>
            <button
              className={page === "review" ? "active" : ""}
              onClick={() => setPage("review")}
            >
              Review Queue
            </button>
            {onboarded && (
              <button className="ghost" type="button" onClick={replayTour}>
                Replay tour
              </button>
            )}
          </nav>
        </header>
        <div key={page} className="page-transition">
          {page === "chat" ? (
            <BentoGrid
              layout="chat"
              className={debugOpen ? "bento-grid--chat-debug-open" : "bento-grid--chat-debug-closed"}
            >
              <ConversationRail
                conversations={conversations}
                activeId={activeId}
                onSelect={select}
                onCreate={create}
                onRemove={remove}
              />
              <BentoTile span="chat" noPad>
                {active && (
                  <Chat
                    key={`${activeId}-${catalogId}`}
                    sessionId={active.id}
                    country={country}
                    tenantId={catalogId}
                    catalogTitle={catalogTitle}
                    messages={active.messages}
                    cardsByTurn={active.cardsByTurn}
                    initialPrompt={chatPrompt}
                    onInitialPromptConsumed={() => setChatPrompt("")}
                    onCountryChange={setCountry}
                    onMessagesChange={updateActive}
                    onDebug={setDebug}
                    onNewChat={create}
                    onToggleDebug={toggleDebug}
                    debugOpen={debugOpen}
                    onAddProducts={goAddProducts}
                  />
                )}
              </BentoTile>
              {debugOpen && (
                <BentoTile span="debug" title="Retrieval" noPad>
                  <DebugPanel debug={debug} shortlist={shortlist} tenantId={catalogId} />
                </BentoTile>
              )}
            </BentoGrid>
          ) : page === "catalog" ? (
            <Catalog
              key={catalogId}
              tenantId={catalogId}
              title={catalogTitle}
              onTryInChat={tryInChat}
              onGoToChat={() => setPage("chat")}
              onNewCatalog={onNewCatalog}
            />
          ) : (
            <ReviewQueue key={catalogId} tenantId={catalogId} />
          )}
        </div>
      </div>
    </>
  );
}
