import { expect, test } from "@playwright/test";

test("runs an agent, shows RAG evidence, and approves the generated plan", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByText("Backend online")).toBeVisible();
  await expect(page.getByTestId("run-agent")).toBeEnabled();

  const streamResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/workflows/multi-agent/stream"),
  );
  await page.getByTestId("run-agent").click();
  const response = await streamResponse;
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("text/event-stream");
  const result = page.getByTestId("workflow-result");
  await expect(result).toBeVisible({ timeout: 60_000 });
  await expect(result.getByText("合规通过")).toBeVisible();
  await expect(page.getByTestId("sse-event-summary")).toContainText("个实时事件");
  await expect(page.getByTestId("agent-node-supervisor")).toHaveAttribute(
    "data-status",
    "completed",
  );
  await expect(page.getByTestId("agent-node-policy_rag")).toHaveAttribute(
    "data-status",
    "completed",
  );
  await expect(page.getByTestId("agent-node-execution_service")).toHaveAttribute(
    "data-status",
    "completed",
  );

  // React Flow verifies attribution visibility one second after mounting.
  await expect(result.locator(".react-flow__attribution")).toBeVisible();
  await page.waitForTimeout(1_100);
  await page.getByRole("tab", { name: "策略与证据" }).click();
  await expect(page.getByRole("heading", { name: "定价模拟" })).toBeVisible();
  const evidence = page.getByTestId("policy-evidence");
  await expect(evidence.locator(".policy-card").first()).toBeVisible();
  await expect(evidence.getByText(/^RRF /).first()).toBeVisible();
  await expect(evidence.getByText(/^Rerank /).first()).toBeVisible();

  await page.getByTestId("submit-approval").click();
  const started = page.getByTestId("approval-start-result");
  await expect(started).toContainText("PENDING_APPROVAL", { timeout: 60_000 });
  await expect(started).toContainText("thread_id 已由页面内部保存");

  const latestRow = page.locator(".latest-approval-row");
  await expect(latestRow).toBeVisible();
  await latestRow.getByRole("button", { name: /批\s*准/ }).click();

  const dialog = page.getByRole("dialog", { name: "确认批准策略" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "批准并生成草稿" }).click();

  const decision = page.getByTestId("approval-decision-result");
  await expect(decision).toContainText("DRAFT_CREATED", { timeout: 60_000 });
  await expect(decision).toContainText("活动草稿");
  await expect(decision).toContainText("demo-approver");
  await expect(page.locator(".latest-approval-row")).toHaveCount(0);
});
