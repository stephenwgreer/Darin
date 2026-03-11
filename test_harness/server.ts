/**
 * Darin Test Harness — Bun HTTP server
 * Port 4343 (avoids conflict with dashboard on 4242)
 */

import { readFileSync } from "fs";
import { join } from "path";

const PORT = 4343;
const ROOT = import.meta.dir;
const PUBLIC = join(ROOT, "public");
const TRANSCRIPT_PATH = join(ROOT, "..", "test_audio", "test.txt");
const ENV_PATH = join(ROOT, "..", ".env");

// Load .env — strip \r, skip comments/blanks
function loadEnv(path: string): Record<string, string> {
  const env: Record<string, string> = {};
  try {
    const lines = readFileSync(path, "utf8").split("\n");
    for (const raw of lines) {
      const line = raw.replace(/\r$/, "").trim();
      if (!line || line.startsWith("#")) continue;
      const eq = line.indexOf("=");
      if (eq === -1) continue;
      const key = line.slice(0, eq).trim();
      const val = line.slice(eq + 1).trim().replace(/^['"]|['"]$/g, "");
      env[key] = val;
    }
  } catch {
    // .env not found — rely on process.env
  }
  return env;
}

const dotenv = loadEnv(ENV_PATH);
const ANTHROPIC_API_KEY = dotenv.ANTHROPIC_API_KEY ?? process.env.ANTHROPIC_API_KEY ?? "";

function serveFile(filePath: string, contentType: string): Response {
  try {
    const body = readFileSync(filePath);
    return new Response(body, { headers: { "Content-Type": contentType } });
  } catch {
    return new Response("Not Found", { status: 404 });
  }
}

async function handleAnalyze(req: Request): Promise<Response> {
  let body: { transcript?: string; prompt_template?: string };
  try {
    body = await req.json();
  } catch {
    return new Response(JSON.stringify({ error: "Invalid JSON" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const { transcript, prompt_template } = body;
  if (!transcript || !prompt_template) {
    return new Response(JSON.stringify({ error: "transcript and prompt_template are required" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  if (!ANTHROPIC_API_KEY) {
    return new Response(JSON.stringify({ error: "ANTHROPIC_API_KEY not set" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }

  // Fill template
  const prompt = prompt_template.replace("{transcript}", transcript);

  // Call Anthropic API with streaming
  const anthropicResp = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
      Accept: "text/event-stream",
    },
    body: JSON.stringify({
      model: "claude-sonnet-4-6",
      max_tokens: 4096,
      stream: true,
      messages: [{ role: "user", content: prompt }],
    }),
  });

  if (!anthropicResp.ok) {
    const err = await anthropicResp.text();
    return new Response(JSON.stringify({ error: err }), {
      status: anthropicResp.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  // Proxy SSE stream directly to browser
  return new Response(anthropicResp.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "Access-Control-Allow-Origin": "*",
    },
  });
}

const server = Bun.serve({
  port: PORT,
  async fetch(req) {
    const url = new URL(req.url);
    const path = url.pathname;

    // CORS preflight
    if (req.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
        },
      });
    }

    if (path === "/" || path === "/index.html") {
      return serveFile(join(PUBLIC, "index.html"), "text/html; charset=utf-8");
    }
    if (path === "/styles.css") {
      return serveFile(join(PUBLIC, "styles.css"), "text/css");
    }
    if (path === "/app.js") {
      return serveFile(join(PUBLIC, "app.js"), "application/javascript");
    }
    if (path === "/health") {
      return new Response("ok");
    }
    if (path === "/api/transcript") {
      try {
        const transcript = readFileSync(TRANSCRIPT_PATH, "utf8");
        return new Response(JSON.stringify({ transcript }), {
          headers: { "Content-Type": "application/json" },
        });
      } catch {
        return new Response(JSON.stringify({ error: "transcript not found" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }
    }
    if (path === "/api/analyze" && req.method === "POST") {
      return handleAnalyze(req);
    }

    return new Response("Not Found", { status: 404 });
  },
});

console.log(`Darin Test Harness running at http://localhost:${server.port}`);
