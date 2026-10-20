type IconName = "brand" | "trip" | "garage" | "settings";

/** Small, local SVGs keep navigation crisp without an icon-font dependency. */
export default function AppIcon({ name }: { name: IconName }) {
  if (name === "brand")
    return (
      <img
        className="rv-icon rv-logo"
        src="/routevalue-map-cost.svg"
        alt=""
        aria-hidden="true"
      />
    );
  const paths: Record<Exclude<IconName, "brand">, string> = {
    trip: "m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Zm6-3v15m6-12v15",
    garage: "m4 10 2-5h12l2 5M3 10h18v8H3V10Zm3 8v2m12-2v2M6 14h2m8 0h2",
    settings: "M4 7h16M4 17h16M9 4v6m6 4v6",
  };
  return (
    <svg
      className="rv-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name]} />
    </svg>
  );
}
