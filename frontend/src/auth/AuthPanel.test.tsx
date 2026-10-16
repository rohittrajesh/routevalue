import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AuthPanel from "./AuthPanel";

const { signInMock, signUpMock } = vi.hoisted(() => ({
  signInMock: vi.fn(),
  signUpMock: vi.fn(),
}));

vi.mock("./neonClient", () => ({
  getNeonAuthClient: () => ({
    adapter: {
      signIn: { email: signInMock },
      signUp: { email: signUpMock },
    },
  }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  signInMock.mockResolvedValue({ data: {}, error: null });
  signUpMock.mockResolvedValue({ data: {}, error: null });
});

describe("AuthPanel", () => {
  it("renders the sign-in form", () => {
    render(<AuthPanel />);

    expect(
      screen.getByRole("heading", { name: "Sign in" }),
    ).toBeInTheDocument();

    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("submits email/password sign-in", async () => {
    const user = userEvent.setup();
    render(<AuthPanel />);

    await user.type(screen.getByLabelText("Email"), "test@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(signInMock).toHaveBeenCalledWith({
        email: "test@example.com",
        password: "password123",
      });
    });
  });

  it("supports account registration", async () => {
    const user = userEvent.setup();
    render(<AuthPanel />);

    await user.click(
      screen.getByRole("button", {
        name: "Create an account",
      }),
    );

    await user.type(screen.getByLabelText("Name"), "Test User");
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");

    await user.click(screen.getByRole("button", { name: "Create account" }));

    await waitFor(() => {
      expect(signUpMock).toHaveBeenCalledWith({
        name: "Test User",
        email: "new@example.com",
        password: "password123",
      });
    });
  });

  it("shows a safe error for rejected credentials", async () => {
    signInMock.mockResolvedValueOnce({
      data: null,
      error: { message: "Sensitive internal provider detail" },
    });

    const user = userEvent.setup();
    render(<AuthPanel />);

    await user.type(screen.getByLabelText("Email"), "test@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    const alert = await screen.findByRole("alert");

    expect(alert).toHaveTextContent("Sign-in failed");
    expect(alert).not.toHaveTextContent("Sensitive internal");
  });

  it("prevents duplicate submissions while pending", async () => {
    let resolveRequest!: (value: unknown) => void;

    signInMock.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveRequest = resolve;
      }),
    );

    const user = userEvent.setup();
    render(<AuthPanel />);

    await user.type(screen.getByLabelText("Email"), "test@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(signInMock).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole("button", { name: "Please wait..." }),
    ).toBeDisabled();

    resolveRequest({ data: {}, error: null });

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Waiting for session confirmation",
    );
  });
});
