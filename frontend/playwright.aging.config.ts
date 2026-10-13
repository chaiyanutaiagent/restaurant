import { defineConfig } from "@playwright/test";
import documents from "./playwright.documents.config";
export default defineConfig({ ...documents, testMatch: "debt-aging.spec.ts", outputDir: "/private/tmp/restaurant-aging-playwright" });
