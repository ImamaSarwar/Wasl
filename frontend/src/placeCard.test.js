import { test } from "node:test";
import assert from "node:assert/strict";
import { GAP, placeCard, shrinkToFit } from "./placeCard.js";

const view = { width: 1200, height: 640 };
const word = (left, top, w = 60, h = 50) => ({ left, top, right: left + w, bottom: top + h });

function assertGood(pos, w, card, v) {
  assert.ok(pos, "expected a position");
  assert.ok(pos.left >= GAP && pos.top >= GAP, "starts on screen");
  assert.ok(pos.left + card.width <= v.width - GAP && pos.top + card.height <= v.height - GAP, "ends on screen");
  const apart = pos.left + card.width <= w.left || pos.left >= w.right || pos.top + card.height <= w.top || pos.top >= w.bottom;
  assert.ok(apart, "does not cover the word");
}

test("below the word when there is room, above it when there is not", () => {
  const card = { width: 360, height: 300 };
  assert.equal(placeCard(word(500, 100), card, view).top, 150 + GAP);
  assert.equal(placeCard(word(500, 500), card, view).top, 500 - GAP - 300);
});

test("a tall card goes beside a word in the middle of the screen", () => {
  const card = { width: 360, height: 500 };
  const w = word(600, 300);
  const pos = placeCard(w, card, view);
  assertGood(pos, w, card, view);
  assert.equal(pos.left, 600 - GAP - 360);
  const nearLeftEdge = word(40, 300);
  assertGood(placeCard(nearLeftEdge, card, view), nearLeftEdge, card, view);
});

test("whatever position is returned is fully on screen and clear of the word", () => {
  for (const card of [{ width: 360, height: 260 }, { width: 360, height: 520 }, { width: 640, height: 330 }]) {
    for (let x = -20; x <= 1180; x += 40) {
      for (let y = -20; y <= 620; y += 20) {
        const w = word(x, y);
        const pos = placeCard(w, card, view);
        if (pos) assertGood(pos, w, card, view);
      }
    }
  }
});

test("returns null when nothing fits, and shrinking then keeps it on screen", () => {
  const small = { width: 380, height: 400 };
  const card = { width: 360, height: 520 };
  const w = word(100, 200);
  assert.equal(placeCard(w, card, small), null);
  const pos = shrinkToFit(w, card, small);
  assert.ok(pos.scale < 1);
  assert.ok(pos.left >= GAP && pos.left + card.width * pos.scale <= small.width - GAP + 0.01);
  assert.ok(pos.top >= GAP && pos.top + card.height * pos.scale <= small.height - GAP + 0.01);
});
