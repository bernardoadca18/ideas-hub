import assert from "node:assert/strict";
import test from "node:test";
import { mediaIndexerApi } from "../src/api/mediaIndexerClient.ts";

test("Studio submits search on an explicit project using max_results", async () => {
  const original = globalThis.fetch;
  const projectId = "00000000-0000-4000-8000-000000000001";
  const result = {
    session_id: "session",
    temporal_index_id: "index",
    start_seconds: 12,
    end_seconds: 24,
    rank: 1,
  };
  globalThis.fetch = async (url, options) => {
    assert.equal(new URL(url).pathname, `/media-search/projects/${projectId}`);
    assert.equal(options.method, "POST");
    assert.deepEqual(JSON.parse(options.body), {
      query: "paisagem",
      max_results: 20,
    });
    return new Response(JSON.stringify({ results: [result] }), { status: 200 });
  };
  try {
    assert.deepEqual(
      await mediaIndexerApi.searchProject(projectId, "paisagem"),
      [result],
    );
  } finally {
    globalThis.fetch = original;
  }
});

test("Studio retains service errors instead of claiming no results", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () =>
    new Response("Provider unavailable", { status: 502 });
  try {
    await assert.rejects(
      mediaIndexerApi.searchProject("project", "paisagem"),
      /502.*Provider unavailable/,
    );
  } finally {
    globalThis.fetch = original;
  }
});
