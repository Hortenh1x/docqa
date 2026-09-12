"use client";

import { createContext, useContext } from "react";
import type { AccountSession } from "@/lib/api/types";

export type ProofAction = "verify" | "reset";

export const AccountContext = createContext<{
  session: AccountSession | null;
  notice: string | null;
  completedProof: ProofAction | null;
  beginProof: () => void;
  signedIn: (session: AccountSession) => void;
  signOut: () => Promise<void>;
  proofCompleted: (action: ProofAction) => Promise<void>;
}>({ session: null, notice: null, completedProof: null, beginProof: () => {}, signedIn: () => {}, signOut: async () => {}, proofCompleted: async () => {} });
export const useAccount = () => useContext(AccountContext);
