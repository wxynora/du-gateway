/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cream: {
          bg: "#EEF0F3",
          card: "#F5F6F8",
          border: "#DFE3E8",
          text: "#1F2733",
          muted: "#677384",
          accent: "#F4D06F",
          blue: "#B7C7DF",
          pink: "#D5C1D0",
          green: "#BFD4CC",
          danger: "#C65D4E"
        },
      },
      borderRadius: {
        xl2: "18px",
        xl3: "28px",
      },
      boxShadow: {
        soft: "0 8px 20px rgba(24, 34, 46, 0.10)",
        soft2: "0 4px 12px rgba(24, 34, 46, 0.08)",
      },
    },
  },
  darkMode: "class",
  plugins: [],
};

