"use client";

import { useState } from "react";

import type { TranslationQA, Translation } from "@/lib/api";

import styles from "./Reader.module.css";

type QaBadgeProps = {
  translation: Translation;
  qa: TranslationQA | undefined;
  loading: boolean;
  onLoad: () => void;
  onRerun: () => void;
};

export default function QaBadge({
  translation,
  qa,
  loading,
  onLoad,
  onRerun,
}: QaBadgeProps) {
  const [open, setOpen] = useState(false);
  const issues = qa?.results.filter((result) => result.status !== "PASSED") ?? [];

  function toggle() {
    const next = !open;
    setOpen(next);
    if (next && !qa) onLoad();
  }

  return (
    <span className={styles.qaControl} onClick={(event) => event.stopPropagation()}>
      <button
        type="button"
        className={`${styles.qaBadge} ${styles[`qa_${translation.qa_status.toLowerCase()}`]}`}
        onClick={toggle}
        aria-expanded={open}
        title="Show deterministic translation QA"
      >
        QA {translation.qa_status}
      </button>
      {open && (
        <span className={styles.qaPopover}>
          <span className={styles.qaHeading}>
            <strong>Deterministic QA</strong>
            <button type="button" onClick={onRerun} disabled={loading}>
              {loading ? "Checking…" : "Run again"}
            </button>
          </span>
          {loading && !qa ? (
            <span>Loading QA details…</span>
          ) : issues.length === 0 ? (
            <span>No warnings or failures.</span>
          ) : (
            <ul>
              {issues.map((issue) => (
                <li key={issue.id}>
                  <strong>{issue.check_type.replaceAll("_", " ")}</strong>
                  <span>{issue.message}</span>
                </li>
              ))}
            </ul>
          )}
        </span>
      )}
    </span>
  );
}
