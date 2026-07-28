import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CatalogEntry as ApiCatalogEntry,
  createCatalog as createCatalogApi,
  listCatalogs,
  renameCatalog as renameCatalogApi,
} from "../api";

const STORAGE_KEY = "prism-catalogs-v1";
const ACTIVE_KEY = "prism-catalog-active-id";
const LEGACY_TENANT_KEY = "prism-tenant-id";

export const DEMO_CATALOG_ID = "demo";

export type CatalogEntry = {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  productCount?: number;
};

type Store = {
  catalogs: CatalogEntry[];
  activeId: string;
};

function demoEntry(now = Date.now()): CatalogEntry {
  return {
    id: DEMO_CATALOG_ID,
    title: "Demo catalog",
    createdAt: now,
    updatedAt: now,
  };
}

function ensureDemo(catalogs: CatalogEntry[]): CatalogEntry[] {
  if (catalogs.some((c) => c.id === DEMO_CATALOG_ID)) {
    return [
      catalogs.find((c) => c.id === DEMO_CATALOG_ID)!,
      ...catalogs.filter((c) => c.id !== DEMO_CATALOG_ID),
    ];
  }
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

function readActiveId(catalogs: CatalogEntry[]): string {
  try {
    const stored = localStorage.getItem(ACTIVE_KEY);
    if (stored && catalogs.some((c) => c.id === stored)) return stored;
    const legacy = localStorage.getItem(STORAGE_KEY);
    if (legacy) {
      const parsed = JSON.parse(legacy) as Store;
      if (parsed.activeId && catalogs.some((c) => c.id === parsed.activeId)) {
        return parsed.activeId;
      }
    }
    const oldTenant = localStorage.getItem(LEGACY_TENANT_KEY);
    if (oldTenant && catalogs.some((c) => c.id === oldTenant)) return oldTenant;
  } catch {
    /* ignore */
  }
  return DEMO_CATALOG_ID;
}

function loadCache(): Store {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Store;
      if (parsed.catalogs?.length) {
        const catalogs = ensureDemo(parsed.catalogs);
        return { catalogs, activeId: readActiveId(catalogs) };
      }
    }
  } catch {
    /* ignore corrupt storage */
  }
  const catalogs = [demoEntry()];
  return { catalogs, activeId: DEMO_CATALOG_ID };
}

function persistActive(activeId: string) {
  try {
    localStorage.setItem(ACTIVE_KEY, activeId);
  } catch {
    /* ignore */
  }
}

function persistCache(store: Store) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
    persistActive(store.activeId);
  } catch {
    /* ignore */
  }
}

function fromApi(entry: ApiCatalogEntry): CatalogEntry {
  return {
    id: entry.id,
    title: entry.title,
    createdAt: entry.createdAt,
    updatedAt: entry.updatedAt,
    productCount: entry.productCount,
  };
}

export function useCatalogs() {
  const [store, setStore] = useState<Store>(() => loadCache());
  const [ready, setReady] = useState(false);

  useEffect(() => {
    persistCache(store);
  }, [store]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const remote = await listCatalogs();
        if (cancelled) return;
        const catalogs = ensureDemo(remote.map(fromApi));
        setStore((prev) => {
          const activeId = catalogs.some((c) => c.id === prev.activeId)
            ? prev.activeId
            : readActiveId(catalogs);
          return { catalogs, activeId };
        });
      } catch {
        /* keep cached list if server unreachable */
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const active = useMemo(
    () => store.catalogs.find((c) => c.id === store.activeId) ?? store.catalogs[0],
    [store]
  );

  const suggestTitle = useCallback(
    (seed = "New catalog") => nextUniqueTitle(store.catalogs, seed),
    [store.catalogs]
  );

  const create = useCallback(async (title: string) => {
    const entry = fromApi(await createCatalogApi(title.trim() || "New catalog"));
    setStore((prev) => ({
      catalogs: ensureDemo([
        ...prev.catalogs.filter((c) => c.id !== entry.id),
        entry,
      ]),
      activeId: entry.id,
    }));
    return entry.id;
  }, []);

  const select = useCallback((id: string) => {
    setStore((prev) =>
      prev.catalogs.some((c) => c.id === id) ? { ...prev, activeId: id } : prev
    );
  }, []);

  const rename = useCallback(async (id: string, title: string) => {
    if (id === DEMO_CATALOG_ID) return;
    const trimmed = title.trim();
    if (!trimmed) return;
    const entry = fromApi(await renameCatalogApi(id, trimmed));
    setStore((prev) => ({
      ...prev,
      catalogs: prev.catalogs.map((c) => (c.id === id ? entry : c)),
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

  const refresh = useCallback(async () => {
    const remote = await listCatalogs();
    const catalogs = ensureDemo(remote.map(fromApi));
    setStore((prev) => ({
      catalogs,
      activeId: catalogs.some((c) => c.id === prev.activeId)
        ? prev.activeId
        : DEMO_CATALOG_ID,
    }));
  }, []);

  return {
    catalogs: store.catalogs,
    activeId: store.activeId,
    active,
    ready,
    create,
    suggestTitle,
    select,
    rename,
    remove,
    refresh,
  };
}
