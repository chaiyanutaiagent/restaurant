import { defineConfig } from "@playwright/test";
import documents from "./playwright.documents.config";
export default defineConfig({ ...documents, testMatch: "recipe-reviews.spec.ts", outputDir: "/private/tmp/restaurant-reviews-playwright" });
