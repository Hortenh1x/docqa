"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ACCOUNTS_ENABLED, api, errorMessage } from "@/lib/api/client";
import type { AccountSession } from "@/lib/api/types";
import { useAccount } from "./context";

const fields = "mt-1 block w-full rounded-[6px] border border-hairline bg-sheet px-3 py-2 text-base";
const button = "rounded-[6px] bg-stamp px-4 py-2 text-sm text-white disabled:opacity-40";
const links = "text-sm text-stamp underline underline-offset-2";
const headings: Record<string, string> = { login: "Sign in", register: "Create account", "forgot-password": "Recover your account", resend: "Resend verification email", verify: "Choose your password", reset: "Reset your password" };
const passwordPolicy = "Use at least 8 characters, including a letter and a number.";
const googleErrors: Record<string, string> = {
  unavailable: "Google sign-in is temporarily unavailable. Please try again.",
  failed: "Google sign-in could not be completed. Please try again.",
  email_exists: "This email already has a DocQA account. Sign in with your email and password, then choose Connect Google.",
  link_failed: "Google could not be connected. Use the Google account with the same verified email as your DocQA account.",
};

export function AccountScreen({ action = "login" }: { action?: string }) {
  const { session, signedIn, proofCompleted, completedProof, beginProof } = useAccount();
  const [email, setEmail] = useState(session?.user?.email ?? "");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [googleBusy, setGoogleBusy] = useState(false);
  const [googleError, setGoogleError] = useState<string | null>(null);
  const [googleLinked, setGoogleLinked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const token = useRef<string | null>(null);
  const [hasToken, setHasToken] = useState(false);
  const [proofReady, setProofReady] = useState(false);
  const proof = action === "verify" || action === "reset";
  const needsPassword = proof || action === "login" || action === "register";
  const createsPassword = needsPassword && action !== "login";
  const available = session?.registration_available ?? false;
  const offersGoogle = session?.google_available && (action === "login" || action === "register");

  useEffect(() => {
    setPassword("");
    setConfirmation("");
    setError(null);
  }, [action, session?.user?.id]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("google_error");
    setGoogleError(code ? (googleErrors[code] ?? googleErrors.failed) : null);
    setGoogleLinked(params.get("google") === "linked");
  }, [action]);

  useEffect(() => {
    if (!proof) return;
    const readProof = () => {
      const fragment = new URLSearchParams(window.location.hash.slice(1));
      token.current = fragment.get("token");
      setHasToken(!!token.current);
      if (token.current) {
        beginProof();
        setPassword("");
        setConfirmation("");
        setError(null);
        setMessage(null);
      }
      // Keep the proof only in this mounted form. It never enters a request URL or storage.
      window.history.replaceState(window.history.state, "", window.location.pathname);
      setProofReady(true);
    };
    readProof();
    window.addEventListener("hashchange", readProof);
    return () => {
      token.current = null;
      window.removeEventListener("hashchange", readProof);
    };
  }, [proof, action, beginProof]);

  if (!ACCOUNTS_ENABLED) return <p className="py-12 text-sm text-ink-soft">Browser accounts are not enabled on this installation.</p>;
  if (!headings[action]) return <p className="py-12">Account page not found.</p>;
  const mailAction = ["register", "forgot-password", "resend"].includes(action);
  const completed = message || (proof && proofReady && !hasToken && completedProof === action);

  return (
    <section className="mx-auto flex max-w-md flex-col gap-5 py-10">
      <h1 className="font-display text-3xl tracking-tight">{headings[action]}</h1>
      {action === "login" && <p className="text-sm text-ink-soft">Sign in for your private documents. You can explore the public collections as a guest.</p>}
      {action === "register" && <p className="text-sm text-ink-soft">Your account has a private document library. Confirm your email before uploading.</p>}
      {proof && !completed && <p className="text-sm text-ink-soft">Choose the password you will use to sign in. This replaces any earlier password and signs out existing sessions.</p>}
      {googleLinked && session?.user && <p role="status" className="text-sm text-ink-soft">Google is connected. You can use it to sign in.</p>}
      {!available && <p role="status" className="text-sm text-ink-soft">Registration and password recovery are currently unavailable. Existing accounts can still sign in.</p>}
      {proof && !proofReady ? <p role="status" className="text-sm text-ink-soft">Preparing secure link…</p> : completed ? <p role="status" className="text-sm text-ink-soft">{message || "Password saved. Sign in with your new password."}</p> : mailAction && !available ? null : proof && !hasToken ? (
        <p role="alert" className="text-sm text-error">This link is missing its token. Open the full link from your email, or request a new one.</p>
      ) : (
        <form className="flex flex-col gap-4" onSubmit={async event => {
          event.preventDefault();
          if (busy || googleBusy) return;
          if (createsPassword && (Array.from(password).length < 8 || !/\p{L}/u.test(password) || !/\p{Nd}/u.test(password))) {
            setError(passwordPolicy); return;
          }
          if (createsPassword && password !== confirmation) {
            setError("Passwords do not match."); return;
          }
          setBusy(true); setError(null);
          const submittedToken = token.current;
          try {
            const payload = proof ? { token: submittedToken, password, password_confirmation: confirmation } : action === "register" ? { email, password, password_confirmation: confirmation } : needsPassword ? { email, password } : { email };
            const result = await api<AccountSession & { message: string }>(`/v1/auth/${action}`, { method: "POST", body: JSON.stringify(payload) });
            if (proof && token.current !== submittedToken) return;
            setPassword(""); setConfirmation("");
            if (action === "login") signedIn(result);
            else if (proof) { token.current = null; setHasToken(false); await proofCompleted(action); }
            else setMessage(result.message);
          } catch (err) {
            if (proof && token.current !== submittedToken) return;
            setPassword(""); setConfirmation("");
            if (!(err instanceof DOMException && err.name === "AbortError")) setError(errorMessage(err));
          } finally { setBusy(false); }
        }}>
          {!proof && <label className="text-sm">Email<input className={fields} name="email" type="email" autoComplete="email" required maxLength={254} value={email} onChange={e => setEmail(e.target.value)} /></label>}
          {needsPassword && <label className="text-sm">{proof ? "New password" : "Password"}<input className={fields} name="password" type="password" autoComplete={action === "login" ? "current-password" : "new-password"} required minLength={action === "login" ? 1 : 8} value={password} onChange={e => setPassword(e.target.value)} aria-describedby={action === "login" ? undefined : "password-policy"} /></label>}
          {createsPassword && <p id="password-policy" className="text-xs text-ink-soft">{passwordPolicy}</p>}
          {createsPassword && <label className="text-sm">Confirm password<input className={fields} name="password_confirmation" type="password" autoComplete="new-password" required value={confirmation} onChange={e => setConfirmation(e.target.value)} aria-invalid={error === "Passwords do not match." || undefined} aria-describedby={error ? "password-error" : undefined} /></label>}
          {error && <p id="password-error" role="alert" className="text-sm text-error">{error}</p>}
          <button type="submit" disabled={busy || googleBusy} className={button}>{busy ? "Please wait…" : ({ login: "Sign in", register: "Create account", "forgot-password": "Send recovery email", resend: "Send verification email", verify: "Verify email and set password", reset: "Reset password" }[action])}</button>
        </form>
      )}
      {offersGoogle && (!session?.user || session.user.email_verified) && <button
        type="button"
        disabled={busy || googleBusy}
        className="flex min-h-10 items-center justify-center gap-2.5 rounded-[6px] border border-[#747775] bg-white px-3 py-2 text-sm font-medium text-[#1f1f1f] hover:bg-neutral-50 disabled:opacity-40"
        onClick={async () => {
          if (busy || googleBusy) return;
          setGoogleBusy(true); setGoogleError(null);
          try {
            const result = await api<{ authorization_url: string }>("/v1/auth/google/start", {
              method: "POST", body: JSON.stringify({ intent: session?.user ? "link" : "login" }),
            });
            window.location.assign(result.authorization_url);
          } catch (err) {
            if (!(err instanceof DOMException && err.name === "AbortError")) setGoogleError(errorMessage(err));
            setGoogleBusy(false);
          }
        }}
      >
        {/* Official Google mark; preserve its colors and aspect ratio. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/branding/google-g.png" alt="" width={20} height={20.4} className="h-auto w-5 shrink-0" />
        <span>{googleBusy ? "Opening Google…" : session?.user ? "Connect Google" : "Continue with Google"}</span>
      </button>}
      {googleError && <p role="alert" className="text-sm text-error">{googleError}</p>}
      <div className="flex flex-wrap gap-x-5 gap-y-3">
        {action !== "login" && <Link className={links} href="/account">Sign in</Link>}
        {available && action === "login" && <><Link className={links} href="/account/register">Create account</Link><Link className={links} href="/account/forgot-password">Forgot password?</Link></>}
        {available && proof && proofReady && !completed && <Link className={links} href={action === "verify" ? "/account/resend" : "/account/forgot-password"}>Request a new link</Link>}
        <Link className={links} href="/">Continue to documents</Link>
      </div>
    </section>
  );
}
