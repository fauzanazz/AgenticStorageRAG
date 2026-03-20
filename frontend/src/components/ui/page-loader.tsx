function PageLoader() {
  return (
    <div
      className="flex min-h-dvh items-center justify-center"
      style={{ background: "var(--background)" }}
    >
      <div className="flex flex-col items-center gap-4">
        <div className="relative size-10">
          <div
            className="absolute inset-0 rounded-full animate-spin"
            style={{
              border: "2px solid var(--border)",
              borderTopColor: "var(--primary)",
            }}
          />
        </div>
        <p className="text-xs font-medium" style={{ color: "var(--outline)" }}>
          Loading...
        </p>
      </div>
    </div>
  );
}

export { PageLoader };
