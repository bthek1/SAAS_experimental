// These paths render without the app shell (no navbar/sidebar)
const PUBLIC_PATHS = ["/", "/login", "/signup"];
// Share links for respondents, who have no account
const PUBLIC_PREFIXES = ["/take/", "/take-battery/"];

export function isPublicPath(pathname: string): boolean {
  return (
    PUBLIC_PATHS.includes(pathname) ||
    PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix))
  );
}
