"use client";

import { useEffect, useState } from "react";

import {
  ApiError,
  apiRequest,
  type GlossaryScope,
  type GlossaryTerm,
} from "@/lib/api";

import styles from "./Reader.module.css";

type GlossaryPanelProps = {
  paperId: string;
  token: string;
  open: boolean;
  onClose: () => void;
  onAuthFailure: () => void;
};

type Draft = {
  source_term: string;
  target_term: string;
  scope: GlossaryScope;
  case_sensitive: boolean;
  enabled: boolean;
};

const emptyDraft: Draft = {
  source_term: "",
  target_term: "",
  scope: "PAPER",
  case_sensitive: false,
  enabled: true,
};

export default function GlossaryPanel({
  paperId,
  token,
  open,
  onClose,
  onAuthFailure,
}: GlossaryPanelProps) {
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function loadTerms() {
    try {
      setTerms(await apiRequest<GlossaryTerm[]>(`/papers/${paperId}/glossary`, {}, token));
    } catch (requestError: unknown) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        onAuthFailure();
        return;
      }
      setError(requestError instanceof Error ? requestError.message : "Unable to load glossary");
    }
  }

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    void apiRequest<GlossaryTerm[]>(`/papers/${paperId}/glossary`, {}, token)
      .then((loaded) => {
        if (!cancelled) setTerms(loaded);
      })
      .catch((requestError: unknown) => {
        if (cancelled) return;
        if (requestError instanceof ApiError && requestError.status === 401) {
          onAuthFailure();
          return;
        }
        setError(requestError instanceof Error ? requestError.message : "Unable to load glossary");
      });
    return () => {
      cancelled = true;
    };
  }, [open, paperId, token, onAuthFailure]);

  function reset() {
    setDraft(emptyDraft);
    setEditingId(null);
  }

  function edit(term: GlossaryTerm) {
    setEditingId(term.id);
    setDraft({
      source_term: term.source_term,
      target_term: term.target_term,
      scope: term.scope,
      case_sensitive: term.case_sensitive,
      enabled: term.enabled,
    });
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (editingId) {
        await apiRequest<GlossaryTerm>(
          `/glossary/${editingId}`,
          {
            method: "PATCH",
            body: JSON.stringify({
              source_term: draft.source_term,
              target_term: draft.target_term,
              case_sensitive: draft.case_sensitive,
              enabled: draft.enabled,
            }),
          },
          token,
        );
      } else {
        await apiRequest<GlossaryTerm>(
          "/glossary",
          {
            method: "POST",
            body: JSON.stringify({
              ...draft,
              paper_id: draft.scope === "PAPER" ? paperId : null,
              source_language: "en",
              target_language: "zh-CN",
            }),
          },
          token,
        );
      }
      reset();
      await loadTerms();
    } catch (requestError: unknown) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        onAuthFailure();
        return;
      }
      setError(requestError instanceof Error ? requestError.message : "Unable to save glossary term");
    } finally {
      setBusy(false);
    }
  }

  async function remove(term: GlossaryTerm) {
    setBusy(true);
    setError("");
    try {
      await apiRequest<void>(`/glossary/${term.id}`, { method: "DELETE" }, token);
      if (editingId === term.id) reset();
      await loadTerms();
    } catch (requestError: unknown) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        onAuthFailure();
        return;
      }
      setError(requestError instanceof Error ? requestError.message : "Unable to delete glossary term");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;

  return (
    <div className={styles.drawerBackdrop} onMouseDown={onClose}>
      <aside
        className={styles.glossaryDrawer}
        aria-label="Glossary management"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className={styles.drawerHeader}>
          <div>
            <strong>Glossary</strong>
            <span>Paper terms override global terms</span>
          </div>
          <button type="button" onClick={onClose}>Close</button>
        </div>
        {error && <p className={styles.panelErrorInline}>{error}</p>}
        <form className={styles.glossaryForm} onSubmit={(event) => void save(event)}>
          <label>
            Source term
            <input
              required
              value={draft.source_term}
              onChange={(event) => setDraft((current) => ({ ...current, source_term: event.target.value }))}
            />
          </label>
          <label>
            Chinese term
            <input
              required
              value={draft.target_term}
              onChange={(event) => setDraft((current) => ({ ...current, target_term: event.target.value }))}
            />
          </label>
          {!editingId && (
            <label>
              Scope
              <select
                value={draft.scope}
                onChange={(event) => setDraft((current) => ({ ...current, scope: event.target.value as GlossaryScope }))}
              >
                <option value="PAPER">This paper</option>
                <option value="USER_GLOBAL">All my papers</option>
              </select>
            </label>
          )}
          <label className={styles.checkLabel}>
            <input
              type="checkbox"
              checked={draft.case_sensitive}
              onChange={(event) => setDraft((current) => ({ ...current, case_sensitive: event.target.checked }))}
            />
            Case sensitive
          </label>
          <label className={styles.checkLabel}>
            <input
              type="checkbox"
              checked={draft.enabled}
              onChange={(event) => setDraft((current) => ({ ...current, enabled: event.target.checked }))}
            />
            Enabled
          </label>
          <div className={styles.formActions}>
            <button type="submit" disabled={busy}>{editingId ? "Save changes" : "Add term"}</button>
            {editingId && <button type="button" onClick={reset}>Cancel</button>}
          </div>
        </form>
        <div className={styles.glossaryList}>
          {terms.length === 0 && <p>No applicable glossary terms yet.</p>}
          {terms.map((term) => (
            <article key={term.id}>
              <div>
                <strong>{term.source_term}</strong>
                <span>{term.target_term}</span>
              </div>
              <p>
                {term.scope === "PAPER" ? "Paper" : "Global"} · {term.case_sensitive ? "case sensitive" : "case insensitive"} · {term.enabled ? "enabled" : "disabled"}
              </p>
              <div>
                <button type="button" onClick={() => edit(term)}>Edit</button>
                <button type="button" onClick={() => void remove(term)} disabled={busy}>Delete</button>
              </div>
            </article>
          ))}
        </div>
      </aside>
    </div>
  );
}
