"use client";

import { Header } from "@/components/Header";
import { AmbientMotion } from "@/components/AmbientMotion";

interface FlowingShellProps {
  children: React.ReactNode;
  maxWidth?: string;
  className?: string;
}

export function FlowingShell({
  children,
  maxWidth = "max-w-md",
  className = "",
}: FlowingShellProps) {
  return (
    <div className="relative min-h-dvh overflow-hidden bg-gradient-to-b from-[#fff5f7] to-white text-[#4a4a4a]">
      <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden">
        <div data-ambient-blob className="flowing-ambient-blob flowing-amb-a" />
        <div data-ambient-blob className="flowing-ambient-blob flowing-amb-b" />
        <div data-ambient-blob className="flowing-ambient-blob flowing-amb-c" />
        <div data-ambient-blob className="flowing-ambient-blob flowing-amb-d" />
        <div data-ambient-blob className="flowing-ambient-blob flowing-amb-e" />
        <div className="absolute inset-0 bg-white/30 backdrop-blur-[50px] backdrop-saturate-[1.3]" />
      </div>
      <AmbientMotion />

      <Header />

      <main className={`relative z-10 mx-auto flex w-full ${maxWidth} flex-col px-4 pb-10 pt-24 ${className}`}>
        {children}
      </main>

      <style>{`
        .flowing-ambient-blob {
          position: absolute;
          border-radius: 9999px;
          opacity: 0.78;
          animation-timing-function: ease-in-out;
          animation-iteration-count: infinite;
          will-change: transform;
          transform: translateZ(0);
        }
        .flowing-amb-a { width: 750px; height: 750px; left: 45%; top: -30%; background: radial-gradient(circle, rgba(232,160,191,.65) 0%, rgba(232,160,191,.28) 42%, rgba(232,160,191,0) 72%); animation: flowing-amb-1 20s infinite; }
        .flowing-amb-b { width: 580px; height: 580px; left: 5%; top: 45%; background: radial-gradient(circle, rgba(166,148,228,.65) 0%, rgba(166,148,228,.28) 42%, rgba(166,148,228,0) 72%); animation: flowing-amb-2 24s infinite; }
        .flowing-amb-c { width: 460px; height: 460px; left: 60%; top: 42%; background: radial-gradient(circle, rgba(255,210,120,.65) 0%, rgba(255,210,120,.28) 42%, rgba(255,210,120,0) 72%); animation: flowing-amb-3 18s infinite; }
        .flowing-amb-d { width: 640px; height: 640px; left: 15%; top: -5%; background: radial-gradient(circle, rgba(255,180,200,.65) 0%, rgba(255,180,200,.28) 42%, rgba(255,180,200,0) 72%); animation: flowing-amb-4 26s infinite; }
        .flowing-amb-e { width: 520px; height: 520px; left: 30%; top: 35%; background: radial-gradient(circle, rgba(255,240,245,.65) 0%, rgba(255,240,245,.28) 42%, rgba(255,240,245,0) 72%); animation: flowing-amb-5 22s infinite; }
        @keyframes flowing-amb-1 {
          0%, 100% { transform: translate(0, 0) scale(1) rotate(0); }
          15% { transform: translate(-160px, 110px) scale(1.5, .5) rotate(18deg); }
          30% { transform: translate(100px, -200px) scale(.45, 1.7) rotate(-16deg); }
          45% { transform: translate(-190px, -90px) scale(1.4, .62) rotate(26deg); }
          60% { transform: translate(60px, 160px) scale(.55, 1.6) rotate(-22deg); }
          75% { transform: translate(120px, -50px) scale(1.25, 1.25) rotate(10deg); }
          90% { transform: translate(-90px, 60px) scale(.75, .68) rotate(-8deg); }
        }
        @keyframes flowing-amb-2 {
          0%, 100% { transform: translate(0, 0) scale(1) rotate(0); }
          20% { transform: translate(170px, -120px) scale(.5, 1.65) rotate(-25deg); }
          40% { transform: translate(-150px, 160px) scale(1.6, .5) rotate(18deg); }
          60% { transform: translate(70px, -100px) scale(.7, 1.35) rotate(-10deg); }
          80% { transform: translate(-100px, -140px) scale(1.35, .8) rotate(20deg); }
        }
        @keyframes flowing-amb-3 {
          0%, 100% { transform: translate(0, 0) scale(1) rotate(0); }
          16% { transform: translate(-140px, 130px) scale(1.55, .45) rotate(22deg); }
          33% { transform: translate(90px, -170px) scale(.45, 1.7) rotate(-18deg); }
          50% { transform: translate(160px, 70px) scale(1.3, 1.35) rotate(8deg); }
          66% { transform: translate(-100px, -80px) scale(.6, 1) rotate(-30deg); }
          83% { transform: translate(-50px, 120px) scale(1.2, .72) rotate(12deg); }
        }
        @keyframes flowing-amb-4 {
          0%, 100% { transform: translate(0, 0) scale(1) rotate(0); }
          20% { transform: translate(120px, -160px) scale(.5, 1.6) rotate(-28deg); }
          40% { transform: translate(-170px, 100px) scale(1.65, .5) rotate(24deg); }
          60% { transform: translate(-60px, -120px) scale(.68, 1.45) rotate(-8deg); }
          80% { transform: translate(100px, 90px) scale(1.35, .72) rotate(-18deg); }
        }
        @keyframes flowing-amb-5 {
          0%, 100% { transform: translate(0, 0) scale(1) rotate(0); }
          25% { transform: translate(-130px, -110px) scale(1.45, .5) rotate(-12deg); }
          50% { transform: translate(110px, 120px) scale(.5, 1.6) rotate(15deg); }
          75% { transform: translate(-70px, 60px) scale(1.05, 1.2) rotate(-9deg); }
        }
        @media (prefers-reduced-motion: reduce) {
          .flowing-ambient-blob { animation: none; }
        }
      `}</style>
    </div>
  );
}

export function PageHero({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <section className="mb-6 text-center">
      <p className="mx-auto mb-4 inline-flex rounded-full border border-[#e8a0bf]/25 bg-gradient-to-b from-[#fff5f7] to-[#ffe8ee] px-4 py-1.5 text-sm font-medium text-[#d4749d] shadow-[0_2px_8px_rgba(212,116,157,0.06)]">
        {eyebrow}
      </p>
      <h1 className="text-balance text-2xl font-bold leading-tight text-[#4a4a4a] sm:text-3xl">
        {title}
      </h1>
      <p className="mx-auto mt-3 max-w-xl text-balance text-sm leading-6 text-gray-400">
        {description}
      </p>
    </section>
  );
}

export function GlassPanel({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-[28px] border border-[#e8a0bf]/15 bg-white/65 shadow-[0_8px_32px_rgba(232,160,191,0.08)] backdrop-blur-xl ${className}`}>
      {children}
    </section>
  );
}