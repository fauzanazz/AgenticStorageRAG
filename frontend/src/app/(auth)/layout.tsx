/**
 * Auth layout -- split-panel design with brand showcase on the left.
 * Used by /login and /register routes.
 */
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-dvh" style={{ background: "var(--background)" }}>
      {/* Left brand panel */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between p-12 relative overflow-hidden">
        {/* Gradient orbs */}
        <div
          className="absolute -top-32 -left-32 w-96 h-96 rounded-full opacity-20 blur-3xl"
          style={{ background: "radial-gradient(circle, var(--primary) 0%, transparent 70%)" }}
        />
        <div
          className="absolute bottom-0 right-0 w-80 h-80 rounded-full opacity-15 blur-3xl"
          style={{ background: "radial-gradient(circle, var(--tertiary) 0%, transparent 70%)" }}
        />

        {/* Logo */}
        <div className="relative z-10">
          <div className="flex items-center gap-3">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center text-white font-bold text-lg"
              style={{ background: "var(--primary)" }}
            >
              D
            </div>
            <span className="text-xl font-semibold tracking-tight" style={{ color: "var(--foreground)" }}>
              OpenRAG
            </span>
          </div>
        </div>

        {/* Center tagline */}
        <div className="relative z-10 flex-1 flex flex-col justify-center max-w-md">
          <h1 className="text-5xl font-bold leading-tight mb-6" style={{ color: "var(--foreground)" }}>
            Intelligent
            <br />
            <span
              className="bg-clip-text text-transparent"
              style={{ backgroundImage: "linear-gradient(135deg, var(--primary), var(--chart-3))" }}
            >
              Knowledge
            </span>
            <br />
            Discovery
          </h1>
          <p className="text-lg leading-relaxed" style={{ color: "var(--muted-foreground)" }}>
            Transform your documents into an interactive knowledge graph.
            Ask questions, explore connections, and discover insights with
            AI-powered retrieval.
          </p>
        </div>

      </div>

      {/* Right form panel */}
      <div className="flex-1 flex items-center justify-center p-8 lg:p-12">
        {children}
      </div>
    </div>
  );
}
