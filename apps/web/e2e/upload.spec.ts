import { test, expect } from "@playwright/test";

test.describe("Upload flow", () => {
  test("should display the upload page", async ({ page }) => {
    await page.goto("/upload");
    await expect(page).toHaveURL(/upload/);
  });

  test("should navigate to files page", async ({ page }) => {
    await page.goto("/files");
    await expect(page).toHaveURL(/files/);
  });

  test("should display the dashboard", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("body")).toBeVisible();
  });

  test("should display the New Audiobook studio", async ({ page }) => {
    await page.goto("/create");
    await expect(page).toHaveURL(/create/);
  });

  test("should display the Library", async ({ page }) => {
    await page.goto("/library");
    await expect(page).toHaveURL(/library/);
  });
});
