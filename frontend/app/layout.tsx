export const metadata = {
  title: "NXT Reel AI",
  description: "AI Creative Director for short-form video",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
