import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const herouiRoot = new URL("..", import.meta.url);
const herouiPath = fileURLToPath(herouiRoot);
const apiPath = join(herouiPath, "src", "api.ts");
const bridgePath = join(herouiPath, "bridge.py");
const vitePath = join(herouiPath, "vite.config.ts");

test("HeroUI frontend has a dedicated GenericAgent bridge copy", () => {
  assert.equal(existsSync(bridgePath), true);
  const bridge = readFileSync(bridgePath, "utf8");

  assert.match(bridge, /GenericAgent HeroUI Bridge/);
  assert.match(bridge, /HEROUI_BRIDGE_PORT/);
  assert.match(bridge, /APP_DIR \/ "dist"/);
  assert.match(bridge, /make_turn_id/);
  assert.match(bridge, /make_response_id/);
  assert.match(bridge, /"turn_id"/);
  assert.match(bridge, /"responseId"/);
  assert.match(bridge, /"gaTurn"/);
  assert.match(bridge, /"outputs"/);
  assert.match(bridge, /app\.router\.add_post\("\/session\/new", new_session_handler\)/);
  assert.match(bridge, /app\.router\.add_get\("\/session\/\{sid\}\/messages", messages_handler\)/);
});

test("HeroUI api adapter speaks the GA bridge polling contract", () => {
  assert.equal(existsSync(apiPath), true);
  const api = readFileSync(apiPath, "utf8");

  assert.match(api, /\/session\/new/);
  assert.match(api, /\/session\/\$\{encodeURIComponent\(sessionId\)\}\/prompt/);
  assert.match(api, /\/session\/\$\{encodeURIComponent\(sessionId\)\}\/messages\?after=/);
  assert.match(api, /window\.setTimeout\(poll/);
  assert.match(api, /answer\.delta/);
  assert.match(api, /answer\.final/);
  assert.match(api, /turn_id: message\.turn_id/);
  assert.match(api, /response_id: message\.responseId/);
  assert.match(api, /response_id: message\.responseId \|\| message\.response_id/);
  assert.doesNotMatch(api, /new EventSource/);
  assert.doesNotMatch(api, /\/api\/turns\/\$\{encodeURIComponent\(turnId\)\}\/events/);
});

test("Vite development server proxies GA bridge endpoints", () => {
  assert.equal(existsSync(vitePath), true);
  const vite = readFileSync(vitePath, "utf8");

  assert.match(vite, /GA_HEROUI_API_TARGET/);
  assert.match(vite, /14169/);
  assert.match(vite, /"\/session"/);
  assert.match(vite, /"\/sessions"/);
  assert.match(vite, /"\/status"/);
});
