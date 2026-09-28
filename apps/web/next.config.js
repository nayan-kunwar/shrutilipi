/** @type {import('next').NextConfig} */
const path = require("path");

const nextConfig = {
  reactStrictMode: true,

  // Monorepo: @shrutilipi/shared ships raw TypeScript, so Next has to compile it.
  transpilePackages: ["@shrutilipi/shared"],

  // Next 14 needs to be told the workspace root, or it traces the shared
  // package's files against the app dir and build output misses them.
  experimental: {
    outputFileTracingRoot: path.join(__dirname, "../../"),
  },
};

module.exports = nextConfig;
