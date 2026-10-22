import { expect, test } from "@playwright/test";

/**
 * Full MVP path in the browser. Needs the API on :8000 (Vite proxies /api and /health).
 */
test("a new user can walk the MVP without a terminal", async ({ page, request }) => {
  const health = await request.get("http://localhost:8000/health").catch(() => null);
  test.skip(!health?.ok(), "API is not running on :8000");

  await page.goto("/corpora");
  await expect(page.getByRole("heading", { name: "Corpora" })).toBeVisible();

  await page.getByRole("button", { name: /new corpus|create a corpus/i }).first().click();
  await page.getByLabel("Name").fill(`e2e ${Date.now()}`);
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expect(page.getByRole("button", { name: "Upload PDFs" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Preview on one document" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Materialise chunks" })).toBeVisible();
});
