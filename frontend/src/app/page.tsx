"use client";

import { useEffect, useCallback, useState } from "react";
import dynamic from "next/dynamic";
import { useStore } from "@/lib/store";
import { api } from "@/lib/api";
import { useGeolocation } from "@/hooks/useGeolocation";
import { useDeviceOrientation } from "@/hooks/useDeviceOrientation";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useIncidentPolling, useLocationPush } from "@/hooks/useIncident";
import { useElevenLabs } from "@/hooks/useElevenLabs";

import { RadarPulse } from "@/components/RadarPulse";
import { SOSButton } from "@/components/SOSButton";
import { ShieldCounter } from "@/components/ShieldCounter";
import { MiniMap } from "@/components/MiniMap";
import { VoiceWaveform } from "@/components/VoiceWaveform";
import { TranscriptionFeed } from "@/components/TranscriptionFeed";
import { NavigationArrow } from "@/components/NavigationArrow";
import { AllClearButton } from "@/components/AllClearButton";

const ExpandedMap = dynamic(() => import("@/components/ExpandedMap"), {
  ssr: false,
  loading: () => null,
});

export default function HomePage() {
  const {
    token,
    setAuth,
    phase,
    setPhase,
    incident,
    setIncident,
    mapExpanded,
    setMapExpanded,
    liveShields,
    setLiveShields,
    liveConvergence,
    setLiveConvergence,
  } = useStore();

  const { position, error: geoError } = useGeolocation();
  const { heading, requestPermission } = useDeviceOrientation();
  const [shieldCount, setShieldCount] = useState(0);
  const [convergenceLabel, setConvergenceLabel] = useState<string | null>(null);
  const [hovered, setHovered] = useState(false);

  /* ── Auto-auth (dev mock) ──────────────────────────────────────────── */

  useEffect(() => {
    if (token) return;
    api
      .verifyToken({
        firebase_id_token: "+491700000001",
        name: "Demo User",
        role: "person",
        emergency_contact_name: "Emergency Contact",
        emergency_contact_phone: "+491700000000",
      })
      .then((res) => {
        // #region agent log
        fetch('http://127.0.0.1:7327/ingest/93b71a90-5ff3-415f-bd50-6d765b588235',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ba3cdb'},body:JSON.stringify({sessionId:'ba3cdb',runId:'run1',hypothesisId:'H-A',location:'page.tsx:auth-success',message:'auth-success',data:{userId:res.user_id,role:res.role,hasToken:!!res.access_token},timestamp:Date.now()})}).catch(()=>{});
        // #endregion
        setAuth(res.access_token, res.user_id, res.role, res.phone);
      })
      .catch((err) => {
        // #region agent log
        fetch('http://127.0.0.1:7327/ingest/93b71a90-5ff3-415f-bd50-6d765b588235',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ba3cdb'},body:JSON.stringify({sessionId:'ba3cdb',runId:'run1',hypothesisId:'H-A',location:'page.tsx:auth-failed',message:'auth-failed',data:{error:String(err)},timestamp:Date.now()})}).catch(()=>{});
        // #endregion
      });
  }, [token, setAuth]);

  // #region agent log
  useEffect(() => {
    fetch('http://127.0.0.1:7327/ingest/93b71a90-5ff3-415f-bd50-6d765b588235',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ba3cdb'},body:JSON.stringify({sessionId:'ba3cdb',runId:'run1',hypothesisId:'H-B',location:'page.tsx:geo-state',message:'geo-state-changed',data:{hasPosition:!!position,lat:position?.lat,lng:position?.lng,geoError:geoError||null},timestamp:Date.now()})}).catch(()=>{});
  }, [position, geoError]);
  // #endregion

  /* ── Hotspot context — shield count (idle) ─────────────────────────── */

  useEffect(() => {
    if (phase !== "idle" || !position) return;
    const poll = () => {
      api
        .getHotspotContext(position.lat, position.lng)
        .then((ctx) => setShieldCount(ctx.shield_count_nearby))
        .catch(() => {});
    };
    poll();
    const id = setInterval(poll, 30_000);
    return () => clearInterval(id);
  }, [phase, position]);

  /* ── Active-incident wiring ────────────────────────────────────────── */

  const incidentId = phase === "active" ? (incident?.id ?? null) : null;
  useIncidentPolling(incidentId);
  useLocationPush(incidentId, position);

  const trackingToken = incident?.trackingUrl
    ? (incident.trackingUrl.split("/track/").pop() ?? null)
    : null;
  useWebSocket(phase === "active" ? trackingToken : null);

  const voice = useElevenLabs(incidentId);

  /* ── Convergence address label ─────────────────────────────────────── */

  useEffect(() => {
    if (!incidentId) return;
    const load = () => {
      api
        .getIncidentContext(incidentId)
        .then((ctx) => setConvergenceLabel(ctx.convergence_address))
        .catch(() => {});
    };
    load();
    const id = setInterval(load, 15_000);
    return () => clearInterval(id);
  }, [incidentId]);

  const convergence = liveConvergence ?? incident?.convergencePoint ?? null;

  /* ── SOS trigger ───────────────────────────────────────────────────── */

  const handleSOS = useCallback(async () => {
    // #region agent log
    fetch('http://127.0.0.1:7327/ingest/93b71a90-5ff3-415f-bd50-6d765b588235',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ba3cdb'},body:JSON.stringify({sessionId:'ba3cdb',runId:'run1',hypothesisId:'H-C',location:'page.tsx:handleSOS-entry',message:'sos-clicked',data:{hasPosition:!!position,hasToken:!!token,phase},timestamp:Date.now()})}).catch(()=>{});
    // #endregion
    if (!position || !token) return;

    try {
      await requestPermission();

      const res = await api.triggerSOS({
        lat: position.lat,
        lng: position.lng,
      });

      // #region agent log
      fetch('http://127.0.0.1:7327/ingest/93b71a90-5ff3-415f-bd50-6d765b588235',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ba3cdb'},body:JSON.stringify({sessionId:'ba3cdb',runId:'run1',hypothesisId:'H-D',location:'page.tsx:handleSOS-success',message:'sos-api-ok',data:{incident_id:res.incident_id,shields:res.shields_notified,convergence:res.convergence_point,tracking_url:res.tracking_url},timestamp:Date.now()})}).catch(()=>{});
      // #endregion

      setIncident({
        id: res.incident_id,
        trackingToken: res.tracking_url.split("/track/").pop() ?? "",
        convergencePoint: res.convergence_point,
        shieldsNotified: res.shields_notified,
        trackingUrl: res.tracking_url,
      });

      if (res.convergence_point) setLiveConvergence(res.convergence_point);
      setPhase("active");

      // #region agent log
      fetch('http://127.0.0.1:7327/ingest/93b71a90-5ff3-415f-bd50-6d765b588235',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ba3cdb'},body:JSON.stringify({sessionId:'ba3cdb',runId:'run1',hypothesisId:'H-E',location:'page.tsx:phase-to-active',message:'phase-changed-to-active',data:{incidentId:res.incident_id},timestamp:Date.now()})}).catch(()=>{});
      // #endregion

      setTimeout(() => voice.start(), 600);
    } catch (err) {
      // #region agent log
      fetch('http://127.0.0.1:7327/ingest/93b71a90-5ff3-415f-bd50-6d765b588235',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'ba3cdb'},body:JSON.stringify({sessionId:'ba3cdb',runId:'run1',hypothesisId:'H-C',location:'page.tsx:handleSOS-error',message:'sos-failed',data:{error:String(err)},timestamp:Date.now()})}).catch(()=>{});
      // #endregion
    }
  }, [
    position,
    token,
    setIncident,
    setPhase,
    setLiveConvergence,
    voice,
    requestPermission,
    phase,
  ]);

  /* ── All clear ─────────────────────────────────────────────────────── */

  const handleAllClear = useCallback(async () => {
    if (!incident?.id) return;
    await voice.stop();
    await api.allClear(incident.id);
    setPhase("resolved");
    setTimeout(() => {
      setPhase("idle");
      setIncident(null);
      setLiveShields([]);
      setLiveConvergence(null);
      setConvergenceLabel(null);
    }, 3_000);
  }, [
    incident,
    voice,
    setPhase,
    setIncident,
    setLiveShields,
    setLiveConvergence,
  ]);

  /* ── Derived ───────────────────────────────────────────────────────── */

  const isIdle = phase === "idle";
  const isActive = phase === "active";
  const isResolved = phase === "resolved";
  const respondingShields = liveShields.filter(
    (s) => s.status === "responding" || s.status === "arrived",
  );

  /* ── Render ────────────────────────────────────────────────────────── */

  return (
    <main className="relative h-dvh w-screen bg-void overflow-hidden">
      {/* ═══════════════════════════════════════ IDLE ═══════════════════ */}
      <div
        className={`absolute inset-0 transition-opacity duration-[400ms] ${
          isIdle ? "opacity-100 z-10" : "opacity-0 z-0 pointer-events-none"
        }`}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <RadarPulse accelerate={hovered} />

        {/* Top bar */}
        <div className="absolute top-0 inset-x-0 flex items-center justify-between px-5 pt-[env(safe-area-inset-top,16px)] pb-3 z-20">
          <span className="font-mono text-[11px] tracking-[3px] text-white/25 uppercase select-none">
            ShieldHer
          </span>
          <ShieldCounter count={shieldCount} />
        </div>

        {/* SOS button */}
        <div className="absolute inset-0 flex items-center justify-center z-10">
          <SOSButton onTrigger={handleSOS} disabled={!position || !token} />
        </div>

        {/* Mini-map */}
        <div className="absolute bottom-[env(safe-area-inset-bottom,24px)] left-6 z-20">
          <MiniMap
            position={position}
            shields={[]}
            convergence={null}
            size={80}
            onExpand={() => setMapExpanded(true)}
          />
        </div>

        {geoError && (
          <div className="absolute bottom-[env(safe-area-inset-bottom,24px)] right-6 z-20">
            <span className="font-mono text-[9px] text-danger/50 tracking-wider">
              GPS UNAVAILABLE
            </span>
          </div>
        )}
      </div>

      {/* ═══════════════════════════════════════ ACTIVE ═════════════════ */}
      <div
        className={`absolute inset-0 transition-opacity duration-[400ms] ${
          isActive ? "opacity-100 z-10" : "opacity-0 z-0 pointer-events-none"
        }`}
      >
        {/* Alert gradient */}
        <div className="absolute inset-0 bg-gradient-to-br from-danger/[0.06] via-void to-void" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,rgba(255,23,68,0.08),transparent_60%)]" />

        <div className="relative z-10 h-full flex flex-col">
          {/* Voice agent */}
          <div className="flex-none pt-[env(safe-area-inset-top,32px)] pb-2 px-6 flex flex-col items-center gap-3">
            <VoiceWaveform isSpeaking={voice.isSpeaking} />
            <p
              className={`font-mono text-[10px] tracking-[2.5px] uppercase ${
                voice.connected
                  ? "text-shield/70"
                  : "text-white/20 animate-blink"
              }`}
            >
              {voice.connected
                ? "SHIELD AGENT CONNECTED"
                : "CONNECTING AGENT..."}
            </p>
            <TranscriptionFeed lines={voice.transcript} />
          </div>

          {/* Navigation arrow */}
          <div className="flex-1 flex items-center justify-center min-h-0">
            <NavigationArrow
              position={position}
              target={convergence}
              heading={heading}
              label={convergenceLabel}
            />
          </div>

          {/* Bottom controls */}
          <div className="flex-none px-6 pb-[env(safe-area-inset-bottom,32px)] flex items-end justify-between">
            <MiniMap
              position={position}
              shields={respondingShields}
              convergence={convergence}
              size={110}
              onExpand={() => setMapExpanded(true)}
            />
            <AllClearButton onConfirm={handleAllClear} />
          </div>
        </div>
      </div>

      {/* ═══════════════════════════════════════ RESOLVED ═══════════════ */}
      <div
        className={`absolute inset-0 flex flex-col items-center justify-center gap-4 bg-void transition-opacity duration-300 ${
          isResolved ? "opacity-100 z-20" : "opacity-0 z-0 pointer-events-none"
        }`}
      >
        <div className="w-20 h-20 rounded-full bg-shield/10 border border-shield/30 flex items-center justify-center animate-fade-in">
          <svg
            className="w-9 h-9 text-shield"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </div>
        <p className="font-display text-2xl text-shield/80 tracking-[5px] animate-slide-up">
          YOU&apos;RE SAFE
        </p>
        <p className="font-mono text-[10px] text-white/25 tracking-wider animate-slide-up">
          NOTIFYING YOUR CONTACTS
        </p>
      </div>

      {/* ═══════════════════════════════════════ MAP OVERLAY ════════════ */}
      {mapExpanded && position && (
        <ExpandedMap
          position={position}
          shields={respondingShields}
          convergence={convergence}
          respondingCount={respondingShields.length}
          onClose={() => setMapExpanded(false)}
        />
      )}
    </main>
  );
}
