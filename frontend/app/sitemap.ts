import type { MetadataRoute } from "next";

const SITE_URL = "https://frontend-six-woad-540yl4bn2c.vercel.app";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: SITE_URL,
      lastModified: new Date(),
      changeFrequency: "weekly",
      priority: 1,
    },
  ];
}
