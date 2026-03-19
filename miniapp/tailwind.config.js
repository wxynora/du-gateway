/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cream: {
          bg: "#FFFBF3",
          card: "#FFF8EE",
          border: "#EDE2C8",
          text: "#2A241B",
          muted: "#6B5E4A",
          accent: "#F4D06F",
          blue: "#95C2E4",
          pink: "#EFAFB7",
          green: "#A9D8AF",
          danger: "#C65D4E"
        },
      },
      borderRadius: {
        xl2: "18px",
        xl3: "28px",
      },
      boxShadow: {
        soft: "0 12px 28px rgba(42, 36, 27, 0.14)",
        soft2: "0 8px 18px rgba(42, 36, 27, 0.12)",
      },
    },
  },
  darkMode: "class",
  plugins: [],
};

