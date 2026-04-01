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
        soft: "6px 6px 14px rgba(170, 180, 194, 0.24), -3px -3px 7px rgba(255, 255, 255, 0.5)",
        soft2: "4px 4px 10px rgba(173, 182, 196, 0.2), -2px -2px 5px rgba(255, 255, 255, 0.42)",
      },
    },
  },
  darkMode: "class",
  plugins: [],
};

