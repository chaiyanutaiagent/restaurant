import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          900: "#0B1F4D",
          700: "#15459A",
          600: "#1265E8",
          100: "#EAF2FF",
          DEFAULT: "#1265E8",
          dark: "#0B1F4D",
          light: "#EAF2FF"
        }
      }
    }
  },
  plugins: [tailwindcssAnimate]
} satisfies Config;
