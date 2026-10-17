import { useEffect, useState, useSyncExternalStore } from 'react';
import { salesKnowledgeApi } from '../../../api/salesKnowledgeApi';
import { createSalesLookupStore } from './customerLookupStore';

/** Customer switches do not affect the sales account's knowledge session. */
export function useSalesLookup(ownerId) {
  // Recreate the store on account changes, so old requests and drafts cannot cross accounts.
  const [scoped, setScoped] = useState(() => ({ ownerId, store: createSalesLookupStore(salesKnowledgeApi) }));
  if (scoped.ownerId !== ownerId) {
    setScoped({ ownerId, store: createSalesLookupStore(salesKnowledgeApi) });
  }
  const { store } = scoped;
  const entries = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const key = ownerId || '';
  useEffect(() => () => store.abort(), [store]);
  return {
    state: entries[key] || {},
    load: (beforeSeq, force) => store.load(key, beforeSeq, force),
    ask: (query) => store.ask(key, query),
    setQuery: (query) => store.setQuery(key, query),
  };
}
