"use client";

import { useState } from "react";

import type { Translation } from "@/lib/api";

import styles from "./Reader.module.css";

type TranslationEditorProps = {
  translation: Translation;
  saving: boolean;
  onCancel: () => void;
  onSave: (value: string) => Promise<void>;
};

export default function TranslationEditor({
  translation,
  saving,
  onCancel,
  onSave,
}: TranslationEditorProps) {
  const [value, setValue] = useState(translation.translated_text ?? "");

  return (
    <span className={styles.translationEditor} onClick={(event) => event.stopPropagation()}>
      <textarea
        value={value}
        onChange={(event) => setValue(event.target.value)}
        rows={6}
        aria-label="Translated text"
      />
      <span>
        <button type="button" onClick={() => void onSave(value)} disabled={saving || !value.trim()}>
          {saving ? "Saving…" : "Save translation"}
        </button>
        <button type="button" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </span>
    </span>
  );
}
