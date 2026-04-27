import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#171717",
        line: "#e5e7eb",
        mint: "#2f8f73",
      },
      boxShadow: {
        soft: "0 8px 24px rgba(23, 23, 23, 0.06)",
      },
    },
  },
  plugins: [],
};

export default config;
