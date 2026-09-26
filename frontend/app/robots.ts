import type { MetadataRoute } from "next";

const SITE_URL = "https://frontend-six-woad-540yl4bn2c.vercel.app";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
