/**
 * Auth layout -- no sidebar, centered content.
 * Used by /login and /register routes.
 */
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <>{children}</>;
}
