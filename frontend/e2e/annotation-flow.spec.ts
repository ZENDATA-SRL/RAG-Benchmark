import { expect, test, type APIRequestContext } from "@playwright/test";

const API = "http://localhost:8000/api/v1";

type Item = { id: string; name: string };

/** A corpus and a configuration with at least one document materialised under it. */
async function materialisedPair(request: APIRequestContext) {
  const corpora = (await (await request.get(`${API}/corpora?limit=50`)).json()).items as Item[];
  const configurations = (
    await (await request.get(`${API}/chunking-configurations?limit=50`)).json()
  ).items as Item[];
  for (const corpus of corpora) {
    for (const configuration of configurations) {
      const coverage = await (
        await request.get(
          `${API}/chunking-configurations/${configuration.id}/coverage?corpus_id=${corpus.id}`,
        )
      ).json();
      if (coverage.ready > 0) return { corpus, configuration };
    }
  }
  return null;
}

/**
 * Write a question in the UI, confirm one evidence chunk, and see the coverage move.
 * Needs the API on :8000 and a corpus with at least one materialised document. It leaves an
 * empty QA set named "e2e annotation …" behind: sets have no delete route.
 */
test("a question is written and its evidence confirmed from the browser", async ({
  page,
  request,
}) => {
  const health = await request.get("http://localhost:8000/health").catch(() => null);
  test.skip(!health?.ok(), "API is not running on :8000");
  const pair = await materialisedPair(request);
  test.skip(!pair, "no corpus has a materialised document");
  const { corpus, configuration } = pair!;

  const qaSet = await (
    await request.post(`${API}/qa-sets`, {
      data: { name: `e2e annotation ${Date.now()}`, origin_corpus_id: corpus.id },
    })
  ).json();

  await page.goto(`/qa-sets/${qaSet.id}`);
  await page.getByRole("button", { name: "New question" }).first().click();
  await page.getByRole("dialog").getByLabel("Question").fill("Where is the e2e evidence?");
  await page.getByRole("button", { name: "Add answer" }).click();
  await page.getByLabel("Expected answer 1").fill("In the first chunk.");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("dialog")).toBeHidden();

  await page.getByTestId("evidence-configuration").selectOption(configuration.id);
  await expect(page.getByTestId("evidence-coverage")).toContainText("1 not reviewed");
  await page.getByRole("link", { name: "Annotate" }).click();

  await expect(page.getByTestId("annotated-question")).toHaveText("Where is the e2e evidence?");
  // The question has no gold document yet: pick a materialised one of the corpus.
  const select = page.getByTestId("annotation-document");
  const options = await select.locator("option").all();
  for (const option of options) {
    await select.selectOption((await option.getAttribute("value"))!);
    const ready = await page
      .getByRole("button", { name: /^Mark chunk \d+ as sufficient$/ })
      .first()
      .isVisible({ timeout: 3000 })
      .catch(() => false);
    if (ready) break;
  }
  await page
    .getByRole("button", { name: /^Mark chunk \d+ as sufficient$/ })
    .first()
    .click();
  await expect(page.getByTestId("evidence-chunks").locator("li")).toHaveCount(1);

  await page.getByPlaceholder("Your name").fill("e2e");
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByTestId("evidence-panel").getByText("confirmed")).toBeVisible();
  await expect(page.getByText(/Decided by e2e/)).toBeVisible();

  await page.getByRole("link", { name: qaSet.name }).click();
  await expect(page.getByTestId("evidence-coverage")).toContainText("1 confirmed");

  // Confirming a chunk made its document a gold document of the question.
  const questions = (await (await request.get(`${API}/qa-sets/${qaSet.id}`)).json()).questions
    .items as { id: string; gold_documents: unknown[] }[];
  expect(questions).toHaveLength(1);
  expect(questions[0].gold_documents).toHaveLength(1);
  await request.delete(`${API}/questions/${questions[0].id}`);
});
