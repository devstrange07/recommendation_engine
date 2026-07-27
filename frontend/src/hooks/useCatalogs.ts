import { useCallback, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "prism-catalogs-v1";
const LEGACY_TENANT_KEY = "prism-tenant-id";

export const DEMO_CATALOG_ID = "demo";

export type CatalogEntry = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
};

type Store = {
  catalogs: CatalogEntry[];
  activeId: string;
};

function newTenantId(): string {
  return `t_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
}

function demoEntry(now = Date.now()): CatalogEntry {
  return {
    id: DEMO_CATALOG_ID,
    title: "Demo catalog",
    createdAt: now,
    updatedAt: now,
  };
}

function ensureDemo(catalogs: CatalogEntry[]): CatalogEntry[] {
  if (catalogs.some((c) => c.id === DEMO_CATALOG_ID)) return catalogs;
  return [demoEntry(), ...catalogs];
}

function nextUniqueTitle(catalogs: CatalogEntry[], requestedTitle: string): string {
  const base = requestedTitle.trim() || "New catalog";
  const used = new Set(catalogs.map((c) => c.title.trim().toLowerCase()));
  if (!used.has(base.toLowerCase())) return base;
  let suffix = 2;
  while (used.has(`${base} ${suffix}`.toLowerCase())) {
    suffix += 1;
  }
  return `${base} ${suffix}`;
}

function loadStore(): Store {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Store;
      if (parsed.catalogs?.length && parsed.activeId) {
        const catalogs = ensureDemo(parsed.catalogs);
        const activeId = catalogs.some((c) => c.id === parsed.activeId)
          ? parsed.activeId
          : DEMO_CATALOG_ID;
        return { catalogs, activeId };
      }
    }
  } catch {
    /* ignore corrupt storage */
  }

  const now = Date.now();
  const catalogs: CatalogEntry[] = [demoEntry(now)];
  const legacy = localStorage.getItem(LEGACY_TENANT_KEY);
  if (legacy && legacy !== DEMO_CATALOG_ID) {
    catalogs.push({
      id: legacy,
      title: "My catalog",
      createdAt: now,
      updatedAt: now,
    });
  }
  return { catalogs, activeId: DEMO_CATALOG_ID };
}

export function useCatalogs() {
  const [store, setStore] = useState<Store>(() => loadStore());

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  }, [store]);

  const active = useMemo(
    () => store.catalogs.find((c) => c.id === store.activeId) ?? store.catalogs[0],
    [store]
  );

  const suggestTitle = useCallback(
    (seed = "New catalog") => nextUniqueTitle(store.catalogs, seed),
    [store.catalogs]
  );

  const create = useCallback((title: string) => {
    const now = Date.now();
    const uniqueTitle = nextUniqueTitle(store.catalogs, title);
    const entry: CatalogEntry = {
      id: newTenantId(),
      title: uniqueTitle,
      createdAt: now,
      updatedAt: now,
    };
    setStore((prev) => ({
      catalogs: [...ensureDemo(prev.catalogs), entry],
      activeId: entry.id,
    }));
    return entry.id;
  }, [store.catalogs]);

  const select = useCallback((id: string) => {
    setStore((prev) =>
      prev.catalogs.some((c) => c.id === id) ? { ...prev, activeId: id } : prev
    );
  }, []);

  const rename = useCallback((id: string, title: string) => {
    if (id === DEMO_CATALOG_ID) return;
    const trimmed = title.trim();
    if (!trimmed) return;
    setStore((prev) => ({
      ...prev,
      catalogs: prev.catalogs.map((c) =>
        c.id === id ? { ...c, title: trimmed, updatedAt: Date.now() } : c
      ),
    }));
  }, []);

  const remove = useCallback((id: string) => {
    if (id === DEMO_CATALOG_ID) return;
    setStore((prev) => {
      const catalogs = ensureDemo(prev.catalogs.filter((c) => c.id !== id));
      const activeId =
        prev.activeId === id ? DEMO_CATALOG_ID : prev.activeId;
      return { catalogs, activeId };
    });
  }, []);

  return {
    catalogs: store.catalogs,
    activeId: store.activeId,
    active,
    create,
    suggestTitle,
    select,
    rename,
    remove,
  };
}
