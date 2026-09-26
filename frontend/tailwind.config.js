/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#FF0033",
          dark: "#CC0029",
          light: "#FF4D66",
        },
      },
    },
  },
  plugins: [],
};
