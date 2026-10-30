import { ButtonItem, PanelSectionRow, TextField } from "@decky/ui";
import { useCallback, useEffect, useState } from "react";
import { searchWiki } from "../api";
import type { WikiSearchResult } from "../types";
import { Notice, Pill, RowButton } from "./Common";

/** Manual compatibility-list picker, for when name matching gets it wrong. */
export function WikiSearch({
  initialQuery,
  current,
  onPick,
}: {
  initialQuery: string;
  current: string | null;
  onPick: (entryName: string) => void | Promise<void>;
}) {
  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<WikiSearchResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [count, setCount] = useState(0);

  const run = useCallback(async (text: string) => {
    if (!text.trim()) {
      setResults([]);
      return;
    }
    try {
      const response = await searchWiki(text, 25);
      setResults(response.results);
      setCount(response.entry_count);
      setError(response.meta?.error ?? null);
    } catch (exc) {
      setError(String(exc));
      setResults([]);
    }
  }, []);

  useEffect(() => {
    void run(initialQuery);
  }, [run, initialQuery]);

  return (
    <>
      <PanelSectionRow>
        <TextField
          label="호환성 목록 검색"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={() => void run(query)}>
          {count > 0 ? `항목 ${count}개 ` : ""}검색
        </ButtonItem>
      </PanelSectionRow>

      {error ? (
        <PanelSectionRow>
          <Notice tone="error">{error}</Notice>
        </PanelSectionRow>
      ) : null}

      {current ? (
        <PanelSectionRow>
          <Notice tone="info">
            <b>{current}</b> 항목으로 고정되어 있습니다. 바꾸려면 다른 항목을 고르십시오.
          </Notice>
        </PanelSectionRow>
      ) : null}

      {results === null ? (
        <PanelSectionRow>
          <div style={{ opacity: 0.6, fontSize: "13px" }}>검색 중…</div>
        </PanelSectionRow>
      ) : results.length === 0 ? (
        <PanelSectionRow>
          <div style={{ opacity: 0.6, fontSize: "13px" }}>일치하는 항목이 없습니다.</div>
        </PanelSectionRow>
      ) : (
        results.map((result) => (
          <RowButton
            key={result.name}
            label={result.name}
            description={result.inputs || undefined}
            right={<Pill>{result.compatibility}</Pill>}
            onClick={() => void onPick(result.name)}
          />
        ))
      )}
    </>
  );
}
