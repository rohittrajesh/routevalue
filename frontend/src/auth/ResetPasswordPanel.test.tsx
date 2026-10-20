import { StrictMode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import ResetPasswordPanel from "./ResetPasswordPanel";
import { getSessionBoundary } from "./sessionBoundary";

const { reset, signOut } = vi.hoisted(() => ({
  reset: vi.fn(),
  signOut: vi.fn(),
}));
vi.mock("./neonClient", () => ({
  getNeonAuthClient: () => ({ adapter: { resetPassword: reset, signOut } }),
}));

beforeEach(() => {
  vi.clearAllMocks();
  window.history.replaceState(
    null,
    "",
    "/v2/reset-password?token=synthetic-token",
  );
  reset.mockResolvedValue({ data: { status: true }, error: null });
  signOut.mockResolvedValue({ data: { success: true }, error: null });
});

async function enterPasswords(first = "synthetic-password", second = first) {
  const user = userEvent.setup();
  await user.type(
    screen.getByLabelText("New password", { exact: true }),
    first,
  );
  await user.type(screen.getByLabelText("Confirm new password"), second);
  await user.click(screen.getByRole("button", { name: "Update password" }));
  return user;
}

it("survives StrictMode, removes URL secrets, calls the SDK, and ends the old session", async () => {
  render(
    <StrictMode>
      <ResetPasswordPanel />
    </StrictMode>,
  );
  expect(window.location.search).toBe("");
  expect(screen.queryByText("synthetic-token")).not.toBeInTheDocument();
  await enterPasswords();
  expect(await screen.findByRole("status")).toHaveTextContent(
    "password was updated",
  );
  expect(reset).toHaveBeenCalledExactlyOnceWith({
    newPassword: "synthetic-password",
    token: "synthetic-token",
  });
  expect(signOut).toHaveBeenCalledOnce();
  expect(getSessionBoundary().reason).toBe("expired");
  expect(
    screen.getByRole("link", { name: "Return to sign in" }),
  ).toHaveAttribute("href", "/v2");
  expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
});

it.each([
  "",
  "?token=",
  "?token=a&token=b",
  "?token=a&error=INVALID_TOKEN",
  `?token=${"a".repeat(2049)}`,
])("rejects invalid reset URL %s", (query) => {
  window.history.replaceState(null, "", `/v2/reset-password${query}`);
  render(<ResetPasswordPanel />);
  expect(screen.getByRole("alert")).toHaveTextContent("missing or invalid");
  expect(window.location.search).toBe("");
  expect(
    screen.queryByRole("button", { name: "Update password" }),
  ).not.toBeInTheDocument();
  expect(reset).not.toHaveBeenCalled();
});

it("rejects mismatched passwords without consuming a token", async () => {
  render(<ResetPasswordPanel />);
  await enterPasswords("synthetic-password", "different-password");
  expect(screen.getByRole("alert")).toHaveTextContent("do not match");
  expect(reset).not.toHaveBeenCalled();
});

it("does not claim an expired or rejected token succeeded, and clears entered passwords", async () => {
  reset.mockResolvedValue({
    data: null,
    error: { code: "INVALID_TOKEN", message: "private-token-detail" },
  });
  render(<ResetPasswordPanel />);
  await enterPasswords();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "request a new email",
  );
  expect(screen.getByRole("alert")).not.toHaveTextContent(
    "private-token-detail",
  );
  expect(screen.getByLabelText("New password", { exact: true })).toHaveValue(
    "",
  );
  expect(screen.getByLabelText("Confirm new password")).toHaveValue("");
  expect(signOut).not.toHaveBeenCalled();
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

it("allows sign-out retry without replaying a successful password reset", async () => {
  signOut.mockResolvedValueOnce({ data: null, error: { status: 503 } });
  render(<ResetPasswordPanel />);
  const user = await enterPasswords();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "sign-out could not be confirmed",
  );
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry sign-out" }));
  await waitFor(() => expect(screen.getByRole("link")).toBeInTheDocument());
  expect(reset).toHaveBeenCalledOnce();
  expect(signOut).toHaveBeenCalledTimes(2);
});

it("prevents duplicate requests while a reset is pending", async () => {
  let finish!: (value: unknown) => void;
  reset.mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  render(<ResetPasswordPanel />);
  await enterPasswords();
  expect(screen.getByRole("button", { name: "Please wait..." })).toBeDisabled();
  expect(reset).toHaveBeenCalledOnce();
  finish({ data: { status: true }, error: null });
  await screen.findByRole("status");
});
