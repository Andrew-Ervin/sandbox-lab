import type { ApiContribution } from "ori";

import { getHtml } from "./lib/render";

export const api: ApiContribution = {
  routes: {
    "GET /": (req: Request, ctx) => {
      ctx.logger.info("Dashboard accessed");

      const html = getHtml(req);
      // Wrap with doctype since React doesn't include it
      const fullHtml = `<!DOCTYPE html>\n${html}`;

      return new Response(fullHtml, {
        headers: { "Content-Type": "text/html" },
      });
    },
  },
};
