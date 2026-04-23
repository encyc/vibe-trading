/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // TradingView Dark Theme Colors
        trading: {
          bg: {
            primary: '#131722',      // Main background
            secondary: '#1e222d',    // Panel background
            tertiary: '#2a2e39',     // Hover background
            border: '#363c4e',       // Border color
          },
          text: {
            primary: '#d1d4dc',      // Primary text
            secondary: '#787b86',    // Secondary text
            muted: '#434651',        // Muted text
          },
          accent: {
            blue: '#2962ff',         // Primary accent (blue)
            blueHover: '#1e53e5',
            green: '#089981',        // Buy/positive
            red: '#f23645',          // Sell/negative
            yellow: '#f9a825',       // Warning
          }
        }
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'Monaco', 'Consolas', 'monospace'],
      },
      boxShadow: {
        'panel': '0 1px 4px rgba(0, 0, 0, 0.3)',
        'panel-lg': '0 4px 12px rgba(0, 0, 0, 0.4)',
      }
    },
  },
  plugins: [],
}
