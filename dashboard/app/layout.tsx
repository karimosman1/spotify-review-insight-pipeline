import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Spotify Review Insight",
  description: "Product priority evidence from 100,000 classified Spotify Google Play reviews.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="masthead">
          <div className="inner">
            <h1><a href="/" style={{ textDecoration: "none" }}>Spotify Review Insight</a></h1>
            <p className="sub">
              Where should the next quarter of product effort go? Every number below is read from the
              database by the backend and traces to a saved pipeline calculation.
            </p>
          </div>
        </header>
        {children}
      </body>
    </html>
  );
}
