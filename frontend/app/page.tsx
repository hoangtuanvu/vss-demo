import Link from "next/link";

const MODULES = [
  {
    href: "/upload",
    label: "Upload",
    title: "Upload feed",
    description: "Hand off a clip to start a simulated live camera stream.",
  },
  {
    href: "/monitor",
    label: "Live Monitor",
    title: "Watch the floor",
    description: "Real-time hazard alerts as they're detected, with Q&A on the footage.",
  },
  {
    href: "/stats",
    label: "Stats",
    title: "Shift report",
    description: "Incident counts broken down by hazard type and severity.",
  },
];

export default function Home() {
  return (
    <main className="min-h-screen">
      <div className="hazard-tape h-2 w-full" aria-hidden="true" />
      <div className="mx-auto max-w-4xl px-6 py-16">
        <p className="font-mono text-xs uppercase tracking-[0.3em] text-caution">Live ops console</p>
        <h1 className="mt-4 font-display text-4xl leading-tight sm:text-5xl">
          Warehouse
          <br />
          Safety Monitor
        </h1>
        <p className="mt-4 max-w-xl text-paper/70">
          Hazard detection, triage, and reporting for the warehouse floor — fed by simulated live
          camera footage.
        </p>

        <nav className="mt-12 grid gap-4 sm:grid-cols-3">
          {MODULES.map((module) => (
            <Link
              key={module.href}
              href={module.href}
              className="group block border border-paper/15 bg-panel p-5 transition-colors hover:border-caution"
            >
              <span className="font-mono text-xs uppercase tracking-widest text-paper/50 group-hover:text-caution">
                {module.label}
              </span>
              <h2 className="mt-2 font-display text-lg">{module.title}</h2>
              <p className="mt-2 text-sm text-paper/60">{module.description}</p>
            </Link>
          ))}
        </nav>
      </div>
    </main>
  );
}
