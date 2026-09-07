import { renderToString } from "react-dom/server";

import { DashboardPage } from "./page";

export const getHtml = (req: Request): string =>
  renderToString(
    <DashboardPage
      heading="Hello World"
      message="Welcome to your Dashboard"
      stats={[
        {
          label: "URL",
          value: req.url,
        },
        {
          label: "Method",
          value: req.method,
        },
        {
          label: "Headers",
          value: JSON.stringify(Object.fromEntries(req.headers)),
        },
      ]}
    />
  );
