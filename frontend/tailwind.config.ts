import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#171717",
        line: "#e5e7eb",
        blush: "#f0a7b5",
        "blush-soft": "#fff0f3",
        mint: "#2f8f73",
        "mint-soft": "#e8f6f0",
        rose: "#d76580",
        rosewood: "#9f3f55",
      },
      boxShadow: {
        glow: "0 18px 60px rgba(74, 54, 63, 0.12)",
        soft: "0 8px 24px rgba(23, 23, 23, 0.06)",
      },
    },
  },
  plugins: [],
};

export default config;
