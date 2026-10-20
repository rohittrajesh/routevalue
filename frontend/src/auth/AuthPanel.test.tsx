import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AuthPanel from "./AuthPanel";

const { signInMock, signUpMock, resetRequestMock, verifyMock } = vi.hoisted(
  () => ({
    signInMock: vi.fn(),
    signUpMock: vi.fn(),
    resetRequestMock: vi.fn(),
    verifyMock: vi.fn(),
  }),
);

vi.mock("./neonClient", () => ({
  getNeonAuthClient: () => ({
    adapter: {
      signIn: { email: signInMock },
      signUp: { email: signUpMock },
      emailOtp: {
        requestPasswordReset: resetRequestMock,
        sendVerificationOtp: verifyMock,
      },
    },
  }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  signInMock.mockResolvedValue({ data: {}, error: null });
  signUpMock.mockResolvedValue({ data: {}, error: null });
  resetRequestMock.mockResolvedValue({ data: { status: true }, error: null });
  verifyMock.mockResolvedValue({ data: { status: true }, error: null });
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
    expect(await screen.findByLabelText("Email code")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Verify your email" }),
    ).toBeInTheDocument();
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

it("confirms successful reauthentication but never rejected credentials", async () => {
  const signedIn = vi.fn();
  signInMock.mockResolvedValueOnce({
    error: { code: "invalid_credentials" },
    data: null,
  });
  const user = userEvent.setup();
  render(<AuthPanel onSignedIn={signedIn} />);
  await user.type(screen.getByLabelText("Email"), "test@example.com");
  await user.type(screen.getByLabelText("Password"), "password123");
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  await screen.findByRole("alert");
  expect(signedIn).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  await waitFor(() => expect(signedIn).toHaveBeenCalledOnce());
  expect(screen.getByLabelText("Password")).toHaveValue("");
});

it.each([
  ["Forgot password?", "Send reset email", "reset"],
  ["Resend verification email", "Send verification email", "verify"],
])(
  "requests %s through the SDK without signing in",
  async (link, submit, kind) => {
    const signedIn = vi.fn();
    const user = userEvent.setup();
    render(<AuthPanel onSignedIn={signedIn} />);
    await user.type(screen.getByLabelText("Password"), "discarded-secret");
    await user.click(screen.getByRole("button", { name: link }));
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Email"), "someone@example.test");
    await user.click(screen.getByRole("button", { name: submit }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "If this account is eligible",
    );
    if (kind === "reset")
      expect(resetRequestMock).toHaveBeenCalledWith({
        email: "someone@example.test",
      });
    else
      expect(verifyMock).toHaveBeenCalledWith({
        email: "someone@example.test",
        type: "email-verification",
      });
    expect(signInMock).not.toHaveBeenCalled();
    expect(signedIn).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "I have an account" }));
    expect(screen.getByLabelText("Password")).toHaveValue("");
  },
);

it("keeps provider secrets and account existence out of recovery errors", async () => {
  resetRequestMock.mockResolvedValue({
    data: null,
    error: {
      code: "INTERNAL_ERROR",
      message: "private@example.test secret-token",
    },
  });
  const user = userEvent.setup();
  render(<AuthPanel />);
  await user.click(screen.getByRole("button", { name: "Forgot password?" }));
  await user.type(screen.getByLabelText("Email"), "someone@example.test");
  await user.click(screen.getByRole("button", { name: "Send reset email" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("could not be completed");
  expect(alert).not.toHaveTextContent("private@example.test");
  expect(alert).not.toHaveTextContent("secret-token");
});

it("does not distinguish an unknown email from an eligible recovery request", async () => {
  resetRequestMock.mockResolvedValueOnce({
    data: null,
    error: { code: "USER_NOT_FOUND" },
  });
  const user = userEvent.setup();
  render(<AuthPanel />);
  await user.click(screen.getByRole("button", { name: "Forgot password?" }));
  await user.type(screen.getByLabelText("Email"), "someone@example.test");
  await user.click(screen.getByRole("button", { name: "Send reset email" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "If this account is eligible",
  );
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("takes an unverified sign-in to code entry without claiming sign-in or using the reset endpoint", async () => {
  signInMock.mockResolvedValueOnce({
    data: null,
    error: { code: "EMAIL_NOT_VERIFIED" },
  });
  const signedIn = vi.fn();
  const user = userEvent.setup();
  render(<AuthPanel onSignedIn={signedIn} />);
  await user.type(screen.getByLabelText("Email"), "someone@example.test");
  await user.type(screen.getByLabelText("Password"), "synthetic-password");
  await user.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByLabelText("Email code")).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Verify your email" }),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
  expect(signedIn).not.toHaveBeenCalled();
  expect(resetRequestMock).not.toHaveBeenCalled();
});
