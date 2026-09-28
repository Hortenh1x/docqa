"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ApiError,
  deleteExtraction,
  errorMessage,
  listDocumentExtractions,
  listSchemas,
  patchExtraction,
  requestExtraction,
} from "@/lib/api/client";
import type { DocumentOut, ExtractedField, Extraction, ExtractionSchema, FieldSpec } from "@/lib/api/types";
import { formatCost } from "@/lib/format";
import type { ReaderHighlight } from "@/features/library/DocumentViewer";

/** Values as the user types them; arrays are one item per line. */
function toInput(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.map(String).join("\n");
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

function fromInput(spec: FieldSpec | undefined, raw: string): unknown {
  const text = raw.trim();
  if (!text) return null;
  switch (spec?.type) {
    case "array":
      return text.split("\n").map((s) => s.trim()).filter(Boolean);
    case "boolean":
      return ["true", "yes", "1"].includes(text.toLowerCase());
    case "number":
    case "integer": {
      const n = Number(text.replace(/,/g, ""));
      return Number.isFinite(n) ? n : text;
    }
    default:
      return text;
  }
}

function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) return value.map(String).join(", ");
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

function confidenceLabel(field: ExtractedField): string {
  if (field.edited) return "edited";
  if (field.confidence === null) return "";
  if (field.confidence >= 0.9) return "quoted";
  if (field.confidence >= 0.75) return "quoted · check";
  if (field.confidence >= 0.6) return "value found";
  return "unverified";
}

/** Fields extracted from one document under a chosen schema: run, inspect the evidence,
 *  correct or clear a value, re-run, delete. */
export function FieldsPanel({
  doc,
  writable,
  onShowEvidence,
}: {
  doc: DocumentOut;
  writable: boolean;
  onShowEvidence: (highlight: ReaderHighlight) => void;
}) {
  const queryClient = useQueryClient();
  const schemas = useQuery({ queryKey: ["schemas"], queryFn: listSchemas, retry: false });
  const extractions = useQuery({
    queryKey: ["extractions", doc.id],
    queryFn: () => listDocumentExtractions(doc.id),
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.some((e) => e.status === "pending" || e.status === "processing") ? 2000 : false,
  });
  const [schemaId, setSchemaId] = useState<string>("");
  useEffect(() => {
    if (!schemaId && schemas.data?.length) {
      const existing = extractions.data?.[0]?.schema_id;
      setSchemaId(existing && schemas.data.some((s) => s.id === existing) ? existing : schemas.data[0].id);
    }
  }, [schemaId, schemas.data, extractions.data]);

  const schema = schemas.data?.find((s) => s.id === schemaId) ?? null;
  const extraction = extractions.data?.find((e) => e.schema_id === schemaId) ?? null;
  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ["extractions", doc.id] });
    void queryClient.invalidateQueries({ queryKey: ["schemas"] });
    void queryClient.invalidateQueries({ queryKey: ["budget"] });
  };
  const run = useMutation({
    mutationFn: (force: boolean) => requestExtraction(doc.id, schemaId, force),
    onSettled: invalidate,
  });
  const remove = useMutation({ mutationFn: deleteExtraction, onSettled: invalidate });

  if (schemas.isPending) return <p className="p-5 text-sm text-ink-soft">Loading schemas…</p>;
  if (schemas.isError) {
    return <p role="alert" className="p-5 text-sm text-ink-soft">{errorMessage(schemas.error)}</p>;
  }
  if (!schemas.data?.length) {
    return (
      <div className="p-5 text-sm leading-6 text-ink-soft">
        <p>No extraction schema yet. A schema names the fields you want pulled out of a document — invoice number, total, parties, dates…</p>
        <p className="mt-2"><Link href="/schemas" className="text-stamp underline">Create a schema</Link></p>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-hairline px-5 py-3">
        <label className="text-xs text-ink-soft" htmlFor="fields-schema">Schema</label>
        <select
          id="fields-schema"
          value={schemaId}
          onChange={(e) => setSchemaId(e.target.value)}
          className="min-h-9 rounded-[6px] border border-hairline bg-paper px-2 text-sm"
        >
          {schemas.data.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        {writable && (
          <button
            type="button"
            onClick={() => run.mutate(false)}
            disabled={run.isPending || doc.status !== "ready" || extraction?.status === "processing"}
            className="min-h-9 rounded-[6px] border border-hairline bg-paper px-3 text-sm enabled:hover:border-stamp/40 disabled:opacity-40"
          >
            {extraction ? "Re-run" : "Extract"}
          </button>
        )}
        {writable && extraction && (
          <button
            type="button"
            onClick={() => { if (confirm("Delete this extraction? Edited values go with it.")) remove.mutate(extraction.id); }}
            disabled={remove.isPending}
            className="min-h-9 rounded-[6px] px-3 text-sm text-ink-soft hover:text-error disabled:opacity-40"
          >
            Delete
          </button>
        )}
        <Link href="/schemas" className="ml-auto text-xs text-ink-soft underline decoration-hairline underline-offset-2 hover:text-ink">
          Manage schemas
        </Link>
      </div>
      {run.isError && <p role="alert" className="px-5 pt-3 text-sm text-error">{errorMessage(run.error)}</p>}
      {doc.status !== "ready" && (
        <p className="px-5 pt-3 text-sm text-ink-soft">Fields can be extracted once the document is ready.</p>
      )}
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {!extraction && schema && (
          <p className="text-sm text-ink-soft">
            {writable ? `No values yet. Extract fills the ${schema.fields.length} fields of “${schema.name}” from this document with one model call.` : "No values extracted for this schema."}
          </p>
        )}
        {extraction && schema && (
          <ExtractionView
            extraction={extraction}
            schema={schema}
            writable={writable}
            onShowEvidence={onShowEvidence}
            onForce={() => run.mutate(true)}
          />
        )}
      </div>
    </div>
  );
}

function ExtractionView({
  extraction,
  schema,
  writable,
  onShowEvidence,
  onForce,
}: {
  extraction: Extraction;
  schema: ExtractionSchema;
  writable: boolean;
  onShowEvidence: (highlight: ReaderHighlight) => void;
  onForce: () => void;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<{ name: string; value: string } | null>(null);
  const patch = useMutation({
    mutationFn: (input: { values?: Record<string, unknown>; clear?: string[] }) => patchExtraction(extraction.id, input),
    onSuccess: () => {
      setEditing(null);
      void queryClient.invalidateQueries({ queryKey: ["extractions", extraction.document_id] });
    },
  });
  const specs = new Map(schema.fields.map((f) => [f.name, f]));
  const edited = Object.values(extraction.fields).some((f) => f.edited);
  const generalIssues = extraction.issues.filter((i) => i.field === null);
  const issuesByField = new Map<string, string[]>();
  for (const issue of extraction.issues) {
    if (issue.field) issuesByField.set(issue.field, [...(issuesByField.get(issue.field) ?? []), issue.message]);
  }
  const cost = extraction.cost_usd === null ? null : Number(extraction.cost_usd);

  if (extraction.status === "pending" || extraction.status === "processing") {
    return <p role="status" className="font-data text-xs text-pending">Extracting…</p>;
  }
  if (extraction.status === "failed") {
    return (
      <p role="alert" className="text-sm text-error">
        Extraction failed{extraction.error ? `: ${extraction.error}` : "."}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="font-data text-[11px] text-ink-soft">
        {extraction.model && `${extraction.model} · `}
        {cost !== null && `${formatCost(cost)} · `}
        {extraction.issues.length ? `${extraction.issues.length} ${extraction.issues.length === 1 ? "issue" : "issues"}` : "no issues"}
        {edited && " · contains edits"}
      </p>
      {patch.isError && <p role="alert" className="text-sm text-error">{errorMessage(patch.error)}</p>}
      <dl className="flex flex-col divide-y divide-hairline" aria-label="Extracted fields">
        {schema.fields.map((spec) => {
          const field = extraction.fields[spec.name] ?? { value: null, confidence: null, evidence: null, edited: false };
          const problems = issuesByField.get(spec.name) ?? [];
          const isEditing = editing?.name === spec.name;
          return (
            <div key={spec.name} className="py-3">
              <dt className="flex flex-wrap items-baseline gap-x-2 text-xs text-ink-soft">
                <span className="text-ink">{spec.name.replace(/_/g, " ")}</span>
                <span className="font-data">{spec.type}{spec.required ? " · required" : ""}</span>
                {confidenceLabel(field) && (
                  <span className={`font-data ${field.edited ? "text-stamp" : field.confidence !== null && field.confidence < 0.6 ? "text-pending" : ""}`}>
                    · {confidenceLabel(field)}
                  </span>
                )}
              </dt>
              <dd className="mt-1">
                {isEditing ? (
                  <form
                    className="flex flex-col gap-2"
                    onSubmit={(e) => {
                      e.preventDefault();
                      patch.mutate({ values: { [spec.name]: fromInput(spec, editing.value) } });
                    }}
                  >
                    {spec.type === "array" ? (
                      <textarea
                        aria-label={`${spec.name} value`}
                        value={editing.value}
                        onChange={(e) => setEditing({ name: spec.name, value: e.target.value })}
                        rows={3}
                        className="w-full rounded-[6px] border border-hairline bg-paper px-2 py-1 font-sans text-sm"
                      />
                    ) : (
                      <input
                        aria-label={`${spec.name} value`}
                        value={editing.value}
                        onChange={(e) => setEditing({ name: spec.name, value: e.target.value })}
                        list={spec.type === "enum" ? `enum-${spec.name}` : undefined}
                        className="w-full rounded-[6px] border border-hairline bg-paper px-2 py-1 text-sm"
                      />
                    )}
                    {spec.type === "enum" && spec.enum_values && (
                      <datalist id={`enum-${spec.name}`}>{spec.enum_values.map((v) => <option key={v} value={v} />)}</datalist>
                    )}
                    <div className="flex gap-2">
                      <button type="submit" disabled={patch.isPending} className="min-h-9 rounded-[6px] border border-hairline bg-paper px-3 text-xs disabled:opacity-40">Save</button>
                      <button type="button" onClick={() => setEditing(null)} className="min-h-9 rounded-[6px] px-3 text-xs text-ink-soft hover:text-ink">Cancel</button>
                    </div>
                  </form>
                ) : (
                  <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
                    <span className={`text-sm ${field.value === null ? "text-ink-soft" : ""}`}>{renderValue(field.value)}</span>
                    {field.evidence && (
                      <button
                        type="button"
                        onClick={() =>
                          onShowEvidence({
                            chunkId: field.evidence!.chunk_id,
                            chunkIndex: field.evidence!.chunk_index,
                            pages: field.evidence!.page ? [field.evidence!.page, field.evidence!.page] : null,
                            quotes: [{ start: field.evidence!.start, end: field.evidence!.end, text: field.evidence!.quote }],
                          })
                        }
                        title={field.evidence.quote}
                        className="text-xs text-stamp underline decoration-hairline underline-offset-2"
                      >
                        Show in document{field.evidence.page ? ` (p. ${field.evidence.page})` : ""}
                      </button>
                    )}
                    {writable && (
                      <>
                        <button type="button" onClick={() => setEditing({ name: spec.name, value: toInput(field.value) })} className="text-xs text-ink-soft hover:text-ink">Edit</button>
                        {field.value !== null && (
                          <button type="button" onClick={() => patch.mutate({ clear: [spec.name] })} className="text-xs text-ink-soft hover:text-error">Clear</button>
                        )}
                      </>
                    )}
                  </div>
                )}
                {field.evidence?.quote && !isEditing && (
                  <p className="mt-1 text-xs italic text-ink-soft [overflow-wrap:anywhere]">“{field.evidence.quote}”</p>
                )}
                {problems.map((message) => <p key={message} className="mt-1 text-xs text-pending">{message}</p>)}
              </dd>
            </div>
          );
        })}
      </dl>
      {generalIssues.length > 0 && (
        <ul className="text-xs text-pending" aria-label="Rule issues">
          {generalIssues.map((issue) => <li key={issue.message}>{issue.message}</li>)}
        </ul>
      )}
      {writable && edited && (
        <p className="text-xs text-ink-soft">
          Re-run keeps your edits.{" "}
          <button type="button" onClick={onForce} className="text-stamp underline decoration-hairline underline-offset-2">Re-run and discard edits</button>
        </p>
      )}
    </div>
  );
}
