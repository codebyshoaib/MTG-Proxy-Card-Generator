import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";

// Space Grotesk carries headings; Inter does the work. Both are variable and self-hosted by
// next/font, so there is no third-party font request at runtime.
const spaceGrotesk = Space_Grotesk({ variable: "--font-space-grotesk", subsets: ["latin"] });
const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "MTG Proxy Generator",
  description: "Generate AI proxy cards from a decklist — artwork only, or the whole card.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${spaceGrotesk.variable} ${inter.variable} h-full font-sans antialiased`}
    >
      <body className="min-h-full">{children}</body>
    </html>
  );
}
