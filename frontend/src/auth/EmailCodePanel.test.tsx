import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import EmailCodePanel from "./EmailCodePanel";

const { request, send, verify, reset, signOut } = vi.hoisted(() => ({
  request: vi.fn(),
  send: vi.fn(),
  verify: vi.fn(),
  reset: vi.fn(),
  signOut: vi.fn(),
}));
vi.mock("./neonClient", () => ({
  getNeonAuthClient: () => ({
    adapter: {
      emailOtp: {
        requestPasswordReset: request,
        sendVerificationOtp: send,
        verifyEmail: verify,
        resetPassword: reset,
      },
      signOut,
    },
  }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  for (const method of [request, send, verify, reset, signOut])
    method.mockResolvedValue({ data: { success: true }, error: null });
});

function panel(purpose: "recover" | "verify") {
  const back = vi.fn();
  render(
    <EmailCodePanel
      purpose={purpose}
      initialEmail="someone@example.test"
      onBack={back}
    />,
  );
  return back;
}

async function enterReset(
  password = "synthetic-password",
  confirmation = password,
) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email code"), "000000");
  await user.type(
    screen.getByLabelText("New password", { exact: true }),
    password,
  );
  await user.type(screen.getByLabelText("Confirm new password"), confirmation);
  await user.click(screen.getByRole("button", { name: "Update password" }));
  return user;
}

it("accepts a previously received verification code without sending another email or resetting a password", async () => {
  const back = panel("verify");
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email code"), "000000");
  await user.click(screen.getByRole("button", { name: "Verify email" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Your email was verified",
  );
  expect(verify).toHaveBeenCalledExactlyOnceWith({
    email: "someone@example.test",
    otp: "000000",
  });
  expect(send).not.toHaveBeenCalled();
  expect(reset).not.toHaveBeenCalled();
  expect(signOut).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "I have an account" }));
  expect(back).toHaveBeenCalledWith("someone@example.test");
});

it("requests a reset code then uses the reset endpoint with code and new password, never verification", async () => {
  panel("recover");
  const user = userEvent.setup();
  expect(screen.queryByLabelText("Email code")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Send reset email" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Enter the email code below",
  );
  expect(request).toHaveBeenCalledExactlyOnceWith({
    email: "someone@example.test",
  });
  await enterReset();
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Your password was updated",
  );
  expect(reset).toHaveBeenCalledExactlyOnceWith({
    email: "someone@example.test",
    otp: "000000",
    password: "synthetic-password",
  });
  expect(verify).not.toHaveBeenCalled();
  expect(signOut).toHaveBeenCalledOnce();
  expect(screen.queryByLabelText("Email code")).not.toBeInTheDocument();
});

it("supports an existing reset code and rejects mismatched passwords without using it", async () => {
  panel("recover");
  const user = userEvent.setup();
  await user.click(
    screen.getByRole("button", { name: "I already have a reset code" }),
  );
  await enterReset("synthetic-password", "different-password");
  expect(screen.getByRole("alert")).toHaveTextContent("do not match");
  expect(request).not.toHaveBeenCalled();
  expect(reset).not.toHaveBeenCalled();
});

it.each(["verify", "recover"] as const)(
  "rejects expired %s codes, clears secrets and permits resending",
  async (purpose) => {
    panel(purpose);
    const method = purpose === "verify" ? verify : reset;
    method.mockResolvedValueOnce({
      data: null,
      error: { code: "OTP_EXPIRED", message: "private-detail" },
    });
    const user = userEvent.setup();
    if (purpose === "recover") {
      await user.click(
        screen.getByRole("button", { name: "I already have a reset code" }),
      );
      await enterReset();
      expect(
        screen.getByLabelText("New password", { exact: true }),
      ).toHaveValue("");
    } else {
      await user.type(screen.getByLabelText("Email code"), "000000");
      await user.click(screen.getByRole("button", { name: "Verify email" }));
    }
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "not accepted or has expired",
    );
    expect(screen.getByRole("alert")).not.toHaveTextContent("private-detail");
    expect(screen.getByLabelText("Email code")).toHaveValue("");
    expect(signOut).not.toHaveBeenCalled();
    await user.click(
      screen.getByRole("button", {
        name:
          purpose === "verify" ? "Send verification email" : "Send reset email",
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "If this account is eligible",
    );
  },
);

it("does not replay reset after a failed sign-out and allows only sign-out retry", async () => {
  signOut.mockResolvedValueOnce({ data: null, error: { status: 503 } });
  panel("recover");
  const user = userEvent.setup();
  await user.click(
    screen.getByRole("button", { name: "I already have a reset code" }),
  );
  await enterReset();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "sign-out could not be confirmed",
  );
  expect(
    screen.queryByRole("button", { name: "I have an account" }),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry sign-out" }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "I have an account" }),
    ).toBeInTheDocument(),
  );
  expect(reset).toHaveBeenCalledOnce();
  expect(signOut).toHaveBeenCalledTimes(2);
});

it("disables resend, submit and back while a code is being verified", async () => {
  let finish!: (value: unknown) => void;
  verify.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  panel("verify");
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email code"), "000000");
  await user.click(screen.getByRole("button", { name: "Verify email" }));
  expect(screen.getByRole("button", { name: "Please wait..." })).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Send verification email" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "I have an account" }),
  ).toBeDisabled();
  finish({ data: { status: true }, error: null });
  await screen.findByRole("status");
});

it("does not accept an explicit false-success provider result", async () => {
  verify.mockResolvedValueOnce({ data: { status: false }, error: null });
  panel("verify");
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email code"), "000000");
  await user.click(screen.getByRole("button", { name: "Verify email" }));
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

it("clears a code when its target email changes and validates that email before submitting", async () => {
  panel("verify");
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Email code"), "000000");
  await user.clear(screen.getByLabelText("Email", { exact: true }));
  await user.type(screen.getByLabelText("Email", { exact: true }), "invalid");
  expect(screen.getByLabelText("Email code")).toHaveValue("");
  await user.type(screen.getByLabelText("Email code"), "000000");
  await user.click(screen.getByRole("button", { name: "Verify email" }));
  expect(verify).not.toHaveBeenCalled();
});
