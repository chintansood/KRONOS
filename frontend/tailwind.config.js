/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        parchment: "#F2E9DA",
        ivory: "#F8F3E9",
        sandstone: "#DCCAB0",
        terracotta: {
          DEFAULT: "#B96D50",
          dark: "#9E563B",
          light: "#CE8267",
        },
        copper: {
          DEFAULT: "#A86F45",
          dark: "#8D572F",
          light: "#C58B60",
        },
        espresso: "#30251F",
        charcoal: "#433A32",
        olive: "#7B8062",
        rose: "#C58B7A",
        gold: {
          DEFAULT: "#C69A55",
          light: "#DCB575",
          dark: "#A77E3C",
        },
        homePaper: "#FCE7CC",
      },
      fontFamily: {
        serif: ["'Cormorant Garamond'", "Cinzel", "Playfair Display", "Georgia", "serif"],
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["'JetBrains Mono'", "SF Mono", "Fira Code", "monospace"],
      },
      boxShadow: {
        warm: "0 10px 30px -10px rgba(48, 37, 31, 0.12)",
        "warm-lg": "0 20px 40px -15px rgba(48, 37, 31, 0.18)",
        "warm-inset": "inset 0 2px 4px 0 rgba(48, 37, 31, 0.06)",
        copper: "0 4px 20px -2px rgba(168, 111, 69, 0.25)",
      },
    },
  },
  plugins: [],
}

