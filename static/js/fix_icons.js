// Patch for Google Material Symbols used by django-unfold.
// Unfold loads Material Symbols via a CDN link tag. In environments where the
// CDN is blocked or slow, icons fall back to their ligature text. This script
// ensures the font is loaded before the page renders by forcing a repaint once
// the FontFace promise resolves.
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(function () {
    document.body.classList.add("fonts-loaded");
  });
}
