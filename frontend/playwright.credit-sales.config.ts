import { defineConfig } from "@playwright/test";
import documents from "./playwright.documents.config";
export default defineConfig({ ...documents, testMatch: ["credit-sales.spec.ts", "company-documents.spec.ts"],
  outputDir: "/private/tmp/restaurant-credit-sales-playwright" });
