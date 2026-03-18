/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cream: {
          bg: "#FFFBF3",
          card: "#FFFDF8",
          border: "#EDE2C8",
          text: "#2A241B",
          muted: "#6B5E4A",
          accent: "#F4D06F",
          blue: "#BFD7EA",
          pink: "#F3C6C6",
          danger: "#C65D4E"
        },
      },
      borderRadius: {
        xl2: "18px",
        xl3: "28px",
      },
      boxShadow: {
        soft: "0 10px 30px rgba(42, 36, 27, 0.06)",
        soft2: "0 6px 18px rgba(42, 36, 27, 0.06)",
      },
    },
  },
  darkMode: "class",
  plugins: [],
};

