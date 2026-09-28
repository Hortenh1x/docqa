"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { useCollections } from "@/app/providers";
import { useAccount } from "@/features/account/context";
import {
  ACCOUNTS_ENABLED,
  createSchema,
  deleteSchema,
  errorMessage,
  fetchExtractionsCsv,
  listSchemas,
  listSchemaTemplates,
  updateSchema,
} from "@/lib/api/client";
import type { ExtractionSchema, FieldSpec, FieldType, SchemaInput, SchemaTemplate } from "@/lib/api/types";

const FIELD_TYPES: FieldType[] = ["string", "number", "integer", "date", "boolean", "enum", "array"];

const emptyField = (): FieldSpec => ({
  name: "", type: "string", description: "", required: false, enum_values: null, pattern: null, examples: [],
});

type Draft = { name: string; description: string; fields: FieldSpec[]; rules: string; index_facts: boolean };

const toDraft = (source?: ExtractionSchema | SchemaTemplate): Draft => ({
  name: source?.name ?? "",
  description: source?.description ?? "",
  fields: source ? source.fields.map((f) => ({ ...f })) : [emptyField()],
  rules: source?.rules.join("\n") ?? "",
  index_facts: source && "index_facts" in source ? source.index_facts : false,
});

const toInput = (draft: Draft): SchemaInput => ({
  name: draft.name.trim(),
  description: draft.description.trim() || null,
  fields: draft.fields.map((f) => ({
    ...f,
    name: f.name.trim(),
    description: f.description.trim(),
    enum_values: f.type === "enum" ? (f.enum_values ?? []).map((v) => v.trim()).filter(Boolean) : null,
    pattern: f.pattern?.trim() || null,
    examples: f.examples.map((v) => v.trim()).filter(Boolean),
  })),
  rules: draft.rules.split("\n").map((r) => r.trim()).filter(Boolean),
  index_facts: draft.index_facts,
});

/** Schemas are the user's own field lists; two templates are offered as starting points. */
export function SchemasScreen() {
  const queryClient = useQueryClient();
  const { session } = useAccount();
  const { selected } = useCollections();
  const canWrite = ACCOUNTS_ENABLED ? !!session?.user?.email_verified : true;
  const schemas = useQuery({ queryKey: ["schemas"], queryFn: listSchemas, retry: false, enabled: !ACCOUNTS_ENABLED || !!session?.user });
  const templates = useQuery({ queryKey: ["schema-templates"], queryFn: listSchemaTemplates, staleTime: Infinity, enabled: canWrite });
  const [editing, setEditing] = useState<{ id: string | null; draft: Draft } | null>(null);
  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ["schemas"] });
  const save = useMutation({
    mutationFn: ({ id, draft }: { id: string | null; draft: Draft }) =>
      id ? updateSchema(id, toInput(draft)) : createSchema(toInput(draft)),
    onSuccess: () => { setEditing(null); invalidate(); },
  });
  const remove = useMutation({ mutationFn: deleteSchema, onSettled: invalidate });
  const [exportError, setExportError] = useState<string | null>(null);

  const download = async (schema: ExtractionSchema) => {
    if (!selected) return;
    setExportError(null);
    try {
      const blob = await fetchExtractionsCsv(selected.id, schema.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${schema.name.replace(/[^\w-]+/g, "_")}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setExportError(errorMessage(error));
    }
  };

  if (ACCOUNTS_ENABLED && !session?.user) {
    return (
      <div className="py-16 text-center text-sm text-ink-soft">
        <Link href="/account" className="text-stamp underline">Sign in</Link> to define extraction schemas for your private documents.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl tracking-tight">Extraction schemas</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-soft">
            A schema lists the fields to pull out of a document — typed, described, optionally required — plus rules that must hold between them. Open a document in the Library, choose <em>Fields</em>, pick a schema, and every value comes back with the passage it was read from.
          </p>
        </div>
        {canWrite && !editing && (
          <button type="button" onClick={() => setEditing({ id: null, draft: toDraft() })} className="min-h-11 rounded-[6px] border border-hairline bg-sheet px-3.5 py-2 text-sm hover:border-stamp/40">
            New schema
          </button>
        )}
      </div>

      {canWrite && !editing && templates.data && templates.data.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-ink-soft">
          <span>Start from a template:</span>
          {templates.data.map((template) => (
            <button
              key={template.key}
              type="button"
              onClick={() => setEditing({ id: null, draft: toDraft(template) })}
              title={template.description}
              className="min-h-9 rounded-full border border-hairline bg-sheet px-3 hover:border-stamp/40 hover:text-ink"
            >
              {template.name}
            </button>
          ))}
        </div>
      )}

      {editing && (
        <SchemaForm
          draft={editing.draft}
          isNew={editing.id === null}
          busy={save.isPending}
          error={save.isError ? errorMessage(save.error) : null}
          onChange={(draft) => setEditing({ id: editing.id, draft })}
          onCancel={() => setEditing(null)}
          onSubmit={() => save.mutate(editing)}
        />
      )}

      {schemas.isError && <p role="alert" className="text-sm text-error">{errorMessage(schemas.error)}</p>}
      {exportError && <p role="alert" className="text-sm text-error">{exportError}</p>}
      {remove.isError && <p role="alert" className="text-sm text-error">{errorMessage(remove.error)}</p>}
      {schemas.data && schemas.data.length === 0 && !editing && (
        <p className="py-10 text-center font-display text-2xl text-ink-soft">No schemas yet.</p>
      )}
      {schemas.data && schemas.data.length > 0 && (
        <ul className="flex flex-col gap-3" aria-label="Schemas">
          {schemas.data.map((schema) => (
            <li key={schema.id} className="rounded-[10px] border border-hairline bg-sheet px-5 py-4 shadow-card">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="text-base">{schema.name}</h2>
                  {schema.description && <p className="mt-0.5 text-sm text-ink-soft">{schema.description}</p>}
                  <p className="font-data mt-1 text-xs text-ink-soft">
                    {schema.fields.length} {schema.fields.length === 1 ? "field" : "fields"}
                    {schema.rules.length > 0 && ` · ${schema.rules.length} ${schema.rules.length === 1 ? "rule" : "rules"}`}
                    {schema.index_facts && " · values indexed for Q&A"}
                    {` · ${schema.extraction_count} ${schema.extraction_count === 1 ? "document" : "documents"} extracted`}
                  </p>
                  <p className="font-data mt-2 flex flex-wrap gap-1 text-[11px] text-ink-soft">
                    {schema.fields.map((f) => (
                      <span key={f.name} className="rounded border border-hairline px-1 leading-4" title={f.description || undefined}>
                        {f.name} · {f.type}{f.required ? " *" : ""}
                      </span>
                    ))}
                  </p>
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-1">
                  {selected && schema.extraction_count > 0 && (
                    <button type="button" onClick={() => void download(schema)} className="min-h-9 rounded-[6px] px-3 text-xs text-ink-soft hover:text-ink" title={`CSV of “${schema.name}” values across ${selected.name}`}>
                      Export CSV
                    </button>
                  )}
                  {canWrite && (
                    <>
                      <button type="button" onClick={() => setEditing({ id: schema.id, draft: toDraft(schema) })} className="min-h-9 rounded-[6px] px-3 text-xs text-ink-soft hover:text-ink">Edit</button>
                      <button
                        type="button"
                        onClick={() => { if (confirm(`Delete “${schema.name}”? Its ${schema.extraction_count} extractions go with it.`)) remove.mutate(schema.id); }}
                        disabled={remove.isPending}
                        className="min-h-9 rounded-[6px] px-3 text-xs text-ink-soft hover:text-error disabled:opacity-40"
                      >
                        Delete
                      </button>
                    </>
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SchemaForm({
  draft, isNew, busy, error, onChange, onCancel, onSubmit,
}: {
  draft: Draft; isNew: boolean; busy: boolean; error: string | null;
  onChange: (draft: Draft) => void; onCancel: () => void; onSubmit: () => void;
}) {
  const setField = (index: number, patch: Partial<FieldSpec>) =>
    onChange({ ...draft, fields: draft.fields.map((f, i) => (i === index ? { ...f, ...patch } : f)) });
  const input = "min-h-9 w-full rounded-[6px] border border-hairline bg-paper px-2 py-1 text-sm";
  return (
    <form
      aria-label={isNew ? "New schema" : "Edit schema"}
      className="flex flex-col gap-4 rounded-[10px] border border-hairline bg-sheet px-5 py-4 shadow-card"
      onSubmit={(e) => { e.preventDefault(); onSubmit(); }}
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-xs text-ink-soft">Name
          <input required value={draft.name} onChange={(e) => onChange({ ...draft, name: e.target.value })} className={input} />
        </label>
        <label className="text-xs text-ink-soft">Description
          <input value={draft.description} onChange={(e) => onChange({ ...draft, description: e.target.value })} className={input} />
        </label>
      </div>
      <fieldset className="flex flex-col gap-3">
        <legend className="text-xs text-ink-soft">Fields — snake_case names; the description tells the model what to look for</legend>
        {draft.fields.map((field, index) => (
          <div key={index} className="grid gap-2 rounded-[6px] border border-hairline p-3 sm:grid-cols-[1fr_120px_2fr_auto]">
            <input aria-label="Field name" placeholder="invoice_number" required pattern="[a-z][a-z0-9_]{0,63}" value={field.name} onChange={(e) => setField(index, { name: e.target.value })} className={input} />
            <select aria-label="Field type" value={field.type} onChange={(e) => setField(index, { type: e.target.value as FieldType, enum_values: e.target.value === "enum" ? field.enum_values ?? [] : null })} className={input}>
              {FIELD_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
            <input aria-label="Field description" placeholder="What the field means, as printed on the document" value={field.description} onChange={(e) => setField(index, { description: e.target.value })} className={input} />
            <div className="flex items-center gap-2">
              <label className="flex items-center gap-1 text-xs text-ink-soft">
                <input type="checkbox" checked={field.required} onChange={(e) => setField(index, { required: e.target.checked })} /> required
              </label>
              <button type="button" aria-label={`Remove field ${field.name || index + 1}`} onClick={() => onChange({ ...draft, fields: draft.fields.filter((_, i) => i !== index) })} className="min-h-9 rounded-[6px] px-2 text-xs text-ink-soft hover:text-error">×</button>
            </div>
            {field.type === "enum" && (
              <input aria-label="Enum options" placeholder="options, comma separated" value={(field.enum_values ?? []).join(", ")} onChange={(e) => setField(index, { enum_values: e.target.value.split(",").map((v) => v.trim()) })} className={`${input} sm:col-span-4`} />
            )}
            <details className="text-xs text-ink-soft sm:col-span-4">
              <summary className="cursor-pointer">More (pattern, examples)</summary>
              <div className="mt-2 grid gap-2 sm:grid-cols-2">
                <input aria-label="Pattern" placeholder="regular expression the value must match" value={field.pattern ?? ""} onChange={(e) => setField(index, { pattern: e.target.value || null })} className={input} />
                <input aria-label="Examples" placeholder="examples, comma separated" value={field.examples.join(", ")} onChange={(e) => setField(index, { examples: e.target.value.split(",").map((v) => v.trim()) })} className={input} />
              </div>
            </details>
          </div>
        ))}
        <button type="button" onClick={() => onChange({ ...draft, fields: [...draft.fields, emptyField()] })} className="self-start rounded-[6px] border border-hairline px-3 py-1.5 text-xs hover:border-stamp/40">
          Add field
        </button>
      </fieldset>
      <label className="text-xs text-ink-soft">Rules — one per line, e.g. <code>abs(subtotal + tax - total) &lt; 0.05</code>
        <textarea value={draft.rules} onChange={(e) => onChange({ ...draft, rules: e.target.value })} rows={2} className={`${input} font-data`} />
      </label>
      <label className="flex items-center gap-2 text-xs text-ink-soft">
        <input type="checkbox" checked={draft.index_facts} onChange={(e) => onChange({ ...draft, index_facts: e.target.checked })} />
        Index the extracted values as a passage, so questions like “what is the total of invoice 42” can be answered
      </label>
      {error && <p role="alert" className="text-sm text-error">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={busy} className="min-h-11 rounded-[6px] border border-hairline bg-paper px-3.5 py-2 text-sm hover:border-stamp/40 disabled:opacity-40">
          {isNew ? "Create schema" : "Save changes"}
        </button>
        <button type="button" onClick={onCancel} className="min-h-11 rounded-[6px] px-3.5 py-2 text-sm text-ink-soft hover:text-ink">Cancel</button>
      </div>
    </form>
  );
}
