"use client";

import { useState, useCallback, useRef } from "react";
import { useConversation } from "@elevenlabs/react";
import { api } from "@/lib/api";

interface TranscriptLine {
  role: "agent" | "user";
  text: string;
  ts: number;
}

export function useElevenLabs(incidentId: string | null) {
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [connected, setConnected] = useState(false);
  const contextInterval = useRef<ReturnType<typeof setInterval>>();

  const conversation = useConversation({
    onConnect: () => setConnected(true),
    onDisconnect: () => setConnected(false),
    onMessage: (message) => {
      const msg = message as { message?: string; source?: string };
      if (msg.message) {
        setTranscript((prev) => [
          ...prev,
          {
            role: msg.source === "user" ? "user" : "agent",
            text: msg.message!,
            ts: Date.now(),
          },
        ]);
      }
    },
    onError: (err) => console.error("[ElevenLabs]", err),
  });

  const start = useCallback(async () => {
    if (!incidentId) return;

    try {
      const { signed_url } = await api.getElevenLabsToken(incidentId);

      await conversation.startSession({
        signedUrl: signed_url,
      });

      const injectContext = async () => {
        try {
          const ctx = await api.getIncidentContext(incidentId);
          const summary = [
            `${ctx.shield_count} shields responding.`,
            ctx.nearest_eta
              ? `Nearest shield ${Math.round(ctx.nearest_eta / 60)} min away.`
              : null,
            ctx.convergence_address
              ? `Walk toward ${ctx.convergence_address}.`
              : null,
            ctx.area_safety_note ?? null,
          ]
            .filter(Boolean)
            .join(" ");

          conversation.sendContextualUpdate(summary);
        } catch {
          /* context fetch failed — agent continues without update */
        }
      };

      await injectContext();
      contextInterval.current = setInterval(injectContext, 60_000);
    } catch (err) {
      console.error("[ElevenLabs] Failed to start session:", err);
    }
  }, [incidentId, conversation]);

  const stop = useCallback(async () => {
    clearInterval(contextInterval.current);
    await conversation.endSession();
    setTranscript([]);
  }, [conversation]);

  return {
    start,
    stop,
    connected,
    isSpeaking: conversation.isSpeaking,
    status: conversation.status,
    transcript,
  };
}
