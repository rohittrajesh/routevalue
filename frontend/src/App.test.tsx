import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("App", () => {
  it("renders the trip evaluation inputs", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", {
        name: /choose the route that costs you less/i,
      }),
    ).toBeInTheDocument();

    expect(screen.getByLabelText(/origin/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/destination/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/value of time/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/fuel efficiency/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/gasoline grade/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/gas price/i)).toBeInTheDocument();

    expect(
      screen.getByRole("button", {
        name: /compare routes/i,
      }),
    ).toBeInTheDocument();
  });
});