import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#1a56db",
          dark: "#173ea6",
          light: "#dbeafe"
        }
      }
    }
  },
  plugins: [tailwindcssAnimate]
} satisfies Config;
