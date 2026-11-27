// Where to put the floating word card so that ALL of it is on screen and it does not cover the hovered word.
// Tries below the word, then above, then left, then right. Returns { left, top }, or null if none of the
// four has room (the caller then tries a wider, shorter card).
export const GAP = 8;

const clamp = (v, min, max) => Math.max(min, Math.min(v, max));

export function placeCard(word, card, view) {
  const maxLeft = view.width - card.width - GAP;
  const maxTop = view.height - card.height - GAP;
  if (maxLeft < GAP || maxTop < GAP) return null; // bigger than the screen

  const left = clamp(word.left, GAP, maxLeft);
  if (word.bottom + GAP <= maxTop) return { left, top: Math.max(GAP, word.bottom + GAP) };
  if (word.top - GAP - card.height >= GAP) return { left, top: Math.min(maxTop, word.top - GAP - card.height) };

  // Beside the word: centred on it vertically, then pushed back inside the screen.
  const top = clamp((word.top + word.bottom - card.height) / 2, GAP, maxTop);
  if (word.left - GAP - card.width >= GAP) return { left: word.left - GAP - card.width, top };
  if (word.right + GAP <= maxLeft) return { left: word.right + GAP, top };
  return null;
}

// Last resort for very small screens: shrink the card until it fits, in the half of the screen away from the word.
export function shrinkToFit(word, card, view) {
  const scale = Math.min(1, (view.width - 2 * GAP) / card.width, (view.height - 2 * GAP) / card.height);
  const width = card.width * scale;
  const height = card.height * scale;
  const wordIsLow = (word.top + word.bottom) / 2 > view.height / 2;
  return {
    left: clamp(word.left, GAP, view.width - width - GAP),
    top: wordIsLow ? GAP : view.height - height - GAP,
    scale,
  };
}
