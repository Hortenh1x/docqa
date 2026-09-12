import type { Metadata } from "next";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

export const metadata: Metadata = {
  title: "About · DocQA",
  description: "DocQA operator, contact, license and source code.",
};

function sourceOffer(): { archive: string; sha256: string } | null {
  const directory = path.join(process.cwd(), "public/source");
  if (!existsSync(path.join(directory, "manifest.json"))) return null;
  const offer = JSON.parse(readFileSync(path.join(directory, "manifest.json"), "utf8"));
  if (!/^docqa-source-[a-f0-9]{64}\.tar\.gz$/.test(offer.archive) ||
      !/^[a-f0-9]{64}$/.test(offer.sha256) ||
      !existsSync(path.join(directory, offer.archive))) {
    throw new Error("Invalid source release. Prepare a new release before building.");
  }
  return offer;
}

const linkStyle = "text-stamp underline underline-offset-2 hover:text-ink";

export default function AboutPage() {
  const source = sourceOffer();
  return (
    <article className="max-w-[68ch] pt-10 sm:pt-14">
      <h1 className="font-display text-3xl tracking-tight">About DocQA</h1>
      <p className="mt-5 text-ink-soft">
        DocQA answers questions about documents with citations to their sources.
        It is a project for exploring document Q&amp;A.
      </p>

      <section className="mt-10" aria-labelledby="operator-heading">
        <h2 id="operator-heading" className="font-display text-xl">Operator &amp; contact</h2>
        <dl className="mt-4 grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
          <dt className="text-ink-soft">Operator</dt><dd>Dmytro Bolibok</dd>
          <dt className="text-ink-soft">Country</dt><dd>Germany</dd>
          <dt className="text-ink-soft">Email</dt>
          <dd className="min-w-0 break-words"><a href="mailto:dmytro.bolibok@gmail.com" className={linkStyle}>dmytro.bolibok@gmail.com</a></dd>
        </dl>
      </section>

      <section className="mt-10 border-t border-hairline pt-8" aria-labelledby="source-heading">
        <h2 id="source-heading" className="font-display text-xl">License &amp; source code</h2>
        <p className="mt-4 text-sm leading-6">
          DocQA is free software licensed under the GNU Affero General Public License,
          version 3 (AGPL-3.0-only). You can study, modify and share it under the license terms.
          It comes without warranty.
        </p>
        {source ? (
          <div className="mt-4 text-sm leading-6">
            <p><a className={linkStyle} href={`/source/${source.archive}`} download>Download the corresponding source for this build</a></p>
            <p className="mt-2"><a className={linkStyle} href="/source/LICENSE.txt">Read the GNU AGPL v3 license</a></p>
            <details className="mt-3 text-xs text-ink-soft">
              <summary className="w-fit cursor-pointer py-2">Verify download checksum</summary>
              <p className="mt-1">SHA-256</p>
              <code className="font-data block break-all">{source.sha256}</code>
            </details>
          </div>
        ) : (
          <p className="mt-4 text-sm leading-6">
            A corresponding-source download has not been packaged for this local build.
            The <a className={linkStyle} href="https://www.gnu.org/licenses/agpl-3.0.html">GNU AGPL v3 license</a> is available online.
          </p>
        )}
        <p className="mt-4 text-sm leading-6">
          The <a className={linkStyle} href="https://github.com/Hortenh1x/docqa">DocQA repository on GitHub</a> contains
          the project history. Its latest commit may differ from this build.
        </p>
        <p className="mt-4 text-sm leading-6 text-ink-soft">
          Third-party components retain their own licenses and copyright notices.
          Font notices: <a className={linkStyle} href="/licenses/fraunces-OFL.txt">Fraunces</a>,{" "}
          <a className={linkStyle} href="/licenses/inter-OFL.txt">Inter</a> and{" "}
          <a className={linkStyle} href="/licenses/jetbrainsmono-OFL.txt">JetBrains Mono</a>.
        </p>
      </section>
    </article>
  );
}
