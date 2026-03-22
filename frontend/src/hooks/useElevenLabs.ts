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

  const start = useCallback(async (explicitIncidentId?: string) => {
    const id = explicitIncidentId ?? incidentId;
    // #region agent log
    fetch('http://127.0.0.1:7327/ingest/93b71a90-5ff3-415f-bd50-6d765b588235',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'e095e6'},body:JSON.stringify({sessionId:'e095e6',runId:'run1',hypothesisId:'H1',location:'useElevenLabs.ts:start-entry',message:'voice.start called',data:{explicitIncidentId:explicitIncidentId??null,closureIncidentId:incidentId,resolvedId:id},timestamp:Date.now()})}).catch(()=>{});
    // #endregion
    if (!id) return;

    try {
      // #region agent log
      fetch('http://127.0.0.1:7327/ingest/93b71a90-5ff3-415f-bd50-6d765b588235',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'e095e6'},body:JSON.stringify({sessionId:'e095e6',runId:'run1',hypothesisId:'H2',location:'useElevenLabs.ts:before-token-fetch',message:'fetching elevenlabs token',data:{id},timestamp:Date.now()})}).catch(()=>{});
      // #endregion
      const { signed_url } = await api.getElevenLabsToken(id);
      // #region agent log
      fetch('http://127.0.0.1:7327/ingest/93b71a90-5ff3-415f-bd50-6d765b588235',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'e095e6'},body:JSON.stringify({sessionId:'e095e6',runId:'run1',hypothesisId:'H2',location:'useElevenLabs.ts:after-token-fetch',message:'got signed_url',data:{hasUrl:!!signed_url,urlPrefix:signed_url?.substring(0,40)},timestamp:Date.now()})}).catch(()=>{});
      // #endregion

      // #region agent log
      fetch('http://127.0.0.1:7327/ingest/93b71a90-5ff3-415f-bd50-6d765b588235',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'e095e6'},body:JSON.stringify({sessionId:'e095e6',runId:'run1',hypothesisId:'H3',location:'useElevenLabs.ts:before-startSession',message:'calling conversation.startSession',data:{signedUrl:signed_url?.substring(0,60)},timestamp:Date.now()})}).catch(()=>{});
      // #endregion
      await conversation.startSession({
        signedUrl: signed_url,
      });
      // #region agent log
      fetch('http://127.0.0.1:7327/ingest/93b71a90-5ff3-415f-bd50-6d765b588235',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'e095e6'},body:JSON.stringify({sessionId:'e095e6',runId:'run1',hypothesisId:'H3',location:'useElevenLabs.ts:after-startSession',message:'startSession resolved',data:{},timestamp:Date.now()})}).catch(()=>{});
      // #endregion

      const injectContext = async () => {
        try {
          const ctx = await api.getIncidentContext(id);
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
      // #region agent log
      fetch('http://127.0.0.1:7327/ingest/93b71a90-5ff3-415f-bd50-6d765b588235',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'e095e6'},body:JSON.stringify({sessionId:'e095e6',runId:'run1',hypothesisId:'H2-H3',location:'useElevenLabs.ts:start-catch',message:'start() threw',data:{error:String(err),name:(err as Error)?.name,stack:(err as Error)?.stack?.substring(0,300)},timestamp:Date.now()})}).catch(()=>{});
      // #endregion
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
