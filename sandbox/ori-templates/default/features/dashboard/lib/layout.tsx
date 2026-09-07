interface LayoutProps {
  title: string;
  children: React.ReactNode;
}

export const Layout = ({ title, children }: LayoutProps): React.ReactNode => (
  <html lang="en">
    <head>
      <meta charSet="utf-8" />
      <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
      />
      <title>{title}</title>
    </head>
    <body
      style={{
        fontFamily: "system-ui, sans-serif",
        maxWidth: "800px",
        margin: "0 auto",
        padding: "2rem",
        lineHeight: 1.5,
      }}
    >
      {children}
    </body>
  </html>
);
