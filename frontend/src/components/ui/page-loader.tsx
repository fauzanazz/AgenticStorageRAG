function PageLoader() {
  return (
    <div
      className="flex min-h-dvh items-center justify-center"
      style={{ background: "#0A0A0F" }}
    >
      <div className="flex flex-col items-center gap-4">
        <div className="relative size-10">
          <div
            className="absolute inset-0 rounded-full animate-spin"
            style={{
              border: "2px solid rgba(255,255,255,0.06)",
              borderTopColor: "#6366F1",
            }}
          />
        </div>
        <p className="text-xs font-medium" style={{ color: "rgba(255,255,255,0.3)" }}>
          Loading...
        </p>
      </div>
    </div>
  );
}

export { PageLoader };
