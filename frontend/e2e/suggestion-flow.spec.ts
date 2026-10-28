import { expect, test, type APIRequestContext } from "@playwright/test";

const API = "http://localhost:8000/api/v1";

type Item = { id: string; name: string };

/** A corpus, a configuration and one of the corpus' documents chunked under it. */
async function materialisedDocument(request: APIRequestContext) {
  const corpora = (await (await request.get(`${API}/corpora?limit=50`)).json()).items as Item[];
  const configurations = (
    await (await request.get(`${API}/chunking-configurations?limit=50`)).json()
  ).items as Item[];
  for (const corpus of corpora) {
    const documents = (await (await request.get(`${API}/corpora/${corpus.id}/documents`)).json())
      .items as Item[];
    for (const configuration of configurations) {
      for (const document of documents) {
        const chunks = await request.get(
          `${API}/documents/${document.id}/chunks?chunking_configuration_id=${configuration.id}&limit=1`,
        );
        if (chunks.ok() && (await chunks.json()).total > 0) {
          return { corpus, configuration, document };
        }
      }
    }
  }
  return null;
}

/**
 * Suggest chunks for an imported-like question, then confirm one from the keyboard. Needs
 * the API on :8000 and a worker serving the transfer workflow. It leaves a QA set named
 * "e2e suggestion …" behind: sets have no delete route.
 */
test("a suggested chunk is confirmed from the review queue", async ({ page, request }) => {
  test.setTimeout(120_000);
  const health = await request.get("http://localhost:8000/health").catch(() => null);
  test.skip(!health?.ok(), "API is not running on :8000");
  const found = await materialisedDocument(request);
  test.skip(!found, "no document is chunked under any configuration");
  const { corpus, configuration, document } = found!;

  const qaSet = await (
    await request.post(`${API}/qa-sets`, {
      data: { name: `e2e suggestion ${Date.now()}`, origin_corpus_id: corpus.id },
    })
  ).json();
  const question = await (
    await request.post(`${API}/qa-sets/${qaSet.id}/questions`, {
      data: {
        text: "What does the first page say?",
        expected_answers: [{ text: "The title of the document.", is_primary: true }],
        gold_document_ids: [document.id],
      },
    })
  ).json();
  const job = await (
    await request.post(`${API}/transfers`, {
      data: { qa_set_id: qaSet.id, target_configuration_id: configuration.id },
    })
  ).json();
  expect(job.progress.total).toBe(1);

  await page.goto(`/transfers/${job.id}`);
  await expect(page.getByTestId("start-review")).toHaveText("Start review", { timeout: 60_000 });
  await page.getByTestId("start-review").click();

  await expect(page.getByTestId("candidate").first()).toBeVisible();
  // Nothing is ticked without a source: grade the best candidate, name, confirm with Enter.
  await page.keyboard.press("s");
  await expect(page.getByTestId("evidence-chunks").locator("li")).toHaveCount(1);
  await page.getByPlaceholder("Your name").fill("e2e");
  await page.getByPlaceholder("Your name").blur();
  await page.keyboard.press("Enter");

  // The queue is done, so the review goes back to the job, which counts the decision.
  await expect(page).toHaveURL(new RegExp(`/transfers/${job.id}$`));
  await expect(page.getByTestId("transfer-progress")).toContainText("1/1");
  const evidence = await (
    await request.get(
      `${API}/questions/${question.id}/evidence?chunking_configuration_id=${configuration.id}`,
    )
  ).json();
  expect(evidence.status).toBe("confirmed");
  await request.delete(`${API}/questions/${question.id}`);
});
