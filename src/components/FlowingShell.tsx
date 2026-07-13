"use client";

import { Header } from "@/components/Header";

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
        <div className="flowing-ambient-blob flowing-amb-a" />
        <div className="flowing-ambient-blob flowing-amb-b" />
        <div className="flowing-ambient-blob flowing-amb-c" />
        <div className="flowing-ambient-blob flowing-amb-d" />
        <div className="flowing-ambient-blob flowing-amb-e" />
        <div className="absolute inset-0 bg-white/30 backdrop-blur-[50px] backdrop-saturate-[1.3]" />
      </div>

      <Header />

      <main className={`relative z-10 mx-auto flex w-full ${maxWidth} flex-col px-4 pb-10 pt-24 ${className}`}>
        {children}
      </main>

      <style>{`
        .flowing-ambient-blob {
          position: absolute;
          border-radius: 9999px;
          filter: blur(90px);
          opacity: 0.48;
          animation-timing-function: ease-in-out;
          animation-iteration-count: infinite;
          will-change: transform, border-radius;
        }
        .flowing-amb-a { width: 720px; height: 720px; left: 48%; top: -30%; background: #e8a0bf; animation: flowing-amb-1 20s infinite; }
        .flowing-amb-b { width: 560px; height: 560px; left: 2%; top: 45%; background: #a694e4; animation: flowing-amb-2 24s infinite; }
        .flowing-amb-c { width: 440px; height: 440px; left: 64%; top: 40%; background: #ffd278; animation: flowing-amb-3 18s infinite; }
        .flowing-amb-d { width: 620px; height: 620px; left: 14%; top: -6%; background: #ffb4c8; animation: flowing-amb-4 26s infinite; }
        .flowing-amb-e { width: 500px; height: 500px; left: 30%; top: 35%; background: #fff0f5; animation: flowing-amb-5 22s infinite; }
        @keyframes flowing-amb-1 {
          0%, 100% { transform: translate(0,0) scale(1) rotate(0deg); border-radius: 50%; }
          20% { transform: translate(-130px,90px) scale(1.35,0.55) rotate(15deg); border-radius: 35% 65% 58% 42%; }
          40% { transform: translate(80px,-180px) scale(0.5,1.6) rotate(-12deg); border-radius: 68% 32% 40% 60%; }
          60% { transform: translate(-160px,-70px) scale(1.25,0.7) rotate(22deg); border-radius: 42% 58% 65% 35%; }
          80% { transform: translate(50px,140px) scale(0.6,1.45) rotate(-18deg); border-radius: 60% 40% 35% 65%; }
        }
        @keyframes flowing-amb-2 {
          0%, 100% { transform: translate(0,0) scale(1) rotate(0deg); border-radius: 50%; }
          25% { transform: translate(140px,-100px) scale(0.55,1.5) rotate(-20deg); border-radius: 62% 38% 45% 55%; }
          50% { transform: translate(-120px,130px) scale(1.45,0.55) rotate(14deg); border-radius: 38% 62% 60% 40%; }
          75% { transform: translate(60px,-80px) scale(0.8,1.25) rotate(-8deg); border-radius: 55% 45% 38% 62%; }
        }
        @keyframes flowing-amb-3 {
          0%, 100% { transform: translate(0,0) scale(1) rotate(0deg); border-radius: 50%; }
          25% { transform: translate(-110px,110px) scale(1.4,0.5) rotate(18deg); border-radius: 40% 60% 55% 45%; }
          50% { transform: translate(70px,-150px) scale(0.5,1.55) rotate(-15deg); border-radius: 65% 35% 42% 58%; }
          75% { transform: translate(130px,60px) scale(1.15,1.3) rotate(6deg); border-radius: 50% 50% 60% 40%; }
        }
        @keyframes flowing-amb-4 {
          0%, 100% { transform: translate(0,0) scale(1) rotate(0deg); border-radius: 50%; }
          25% { transform: translate(100px,-130px) scale(0.55,1.5) rotate(-22deg); border-radius: 60% 40% 48% 52%; }
          50% { transform: translate(-140px,80px) scale(1.5,0.55) rotate(20deg); border-radius: 35% 65% 58% 42%; }
          75% { transform: translate(-50px,-100px) scale(0.75,1.2) rotate(-6deg); border-radius: 52% 48% 40% 60%; }
        }
        @keyframes flowing-amb-5 {
          0%, 100% { transform: translate(0,0) scale(1) rotate(0deg); border-radius: 50%; }
          33% { transform: translate(-100px,-90px) scale(1.3,0.6) rotate(-10deg); border-radius: 42% 58% 55% 45%; }
          66% { transform: translate(90px,100px) scale(0.55,1.45) rotate(12deg); border-radius: 62% 38% 40% 60%; }
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