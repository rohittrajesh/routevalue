const METERS_PER_MILE = 1609.344;

export function formatDistance(distanceMeters: number): string {
  const miles = distanceMeters / METERS_PER_MILE;

  return `${miles.toFixed(1)} mi`;
}

export function formatDuration(durationSeconds: number): string {
  const totalMinutes = Math.round(durationSeconds / 60);

  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  if (hours === 0) {
    return `${minutes} min`;
  }

  if (minutes === 0) {
    return `${hours} hr`;
  }

  return `${hours} hr ${minutes} min`;
}

export function formatMoney(value: string | null): string {
  if (value === null) {
    return "Unavailable";
  }

  return `$${Number(value).toFixed(2)}`;
}

export function formatDecisionReason(reason: string | null): string {
  switch (reason) {
    case "faster_and_cheaper":
      return "Faster and cheaper than the next-best personalized-cost alternative.";

    case "faster_route_worth_extra_cost":
      return "Compared with the next-best alternative, the time saved is worth the additional monetary cost.";

    case "cheaper_route_worth_extra_time":
      return "Compared with the next-best alternative, the money saved is worth the additional travel time.";

    case "only_eligible_route":
      return "This is the only route with enough data to evaluate.";

    case "numerical_tie_faster_wins":
      return "The routes were effectively tied, so the faster route won.";

    case "numerical_tie_cheaper_wins":
      return "The routes were effectively tied, so the cheaper route won.";

    case "numerical_tie_shorter_distance_wins":
      return "The routes were effectively tied, so the shorter route won.";

    case "numerical_tie_stable_order_wins":
      return "The routes remained tied after comparison.";

    default:
      return "RouteValue selected the lowest personalized route cost.";
  }
}

export function formatEligibilityReason(
  reason: string | null,
): string {
  switch (reason) {
    case "missing_toll_cost":
      return "Toll information is unavailable for this route.";

    case "missing_energy_estimate":
      return "Fuel-cost information is unavailable for this route.";

    default:
      return "This route does not have enough data to calculate a personalized cost.";
  }
}