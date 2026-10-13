import { defineConfig } from "@playwright/test";
import documents from "./playwright.documents.config";
export default defineConfig({ ...documents, testMatch: "cost-analysis.spec.ts", outputDir: "/private/tmp/restaurant-cost-playwright" });
