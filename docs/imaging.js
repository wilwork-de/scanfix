/**
 * The image maths behind the browser tools, ported from tools/clean_scan.py and
 * tools/extract_signature.py.
 *
 * Nothing in here touches the DOM, a canvas or a file. Every function takes plain
 * typed arrays with a width and a height, which is what lets tests/test_imaging.mjs
 * run the same file under Node: the maths that ships is the maths that is tested.
 *
 * Convention: greyscale buffers are Float32Array of length w*h, 0 = black,
 * 255 = white. Colour buffers are RGBA bytes, four per pixel, as an ImageData.
 */

// --- conversion -------------------------------------------------------------

/** RGBA bytes to luminance. Same ITU-R 601-2 weights Pillow uses for mode "L". */
export function toGrey(rgba, w, h) {
  const out = new Float32Array(w * h);
  for (let i = 0, p = 0; i < out.length; i++, p += 4) {
    out[i] = (rgba[p] * 299 + rgba[p + 1] * 587 + rgba[p + 2] * 114) / 1000;
  }
  return out;
}

/** Greyscale floats back to opaque RGBA bytes. */
export function greyToRgba(grey, w, h) {
  const out = new Uint8ClampedArray(w * h * 4);
  for (let i = 0, p = 0; i < grey.length; i++, p += 4) {
    const v = grey[i];
    out[p] = out[p + 1] = out[p + 2] = v;
    out[p + 3] = 255;
  }
  return out;
}

// --- resampling -------------------------------------------------------------

/**
 * Area-average downscale. Pillow's BILINEAR widens its filter when it shrinks an
 * image, so it averages the pixels it is skipping; a plain bilinear sample would
 * alias badly at 1:8 and leave the illumination estimate speckled.
 */
export function downscale(src, w, h, dw, dh) {
  const out = new Float32Array(dw * dh);
  const sx = w / dw, sy = h / dh;
  for (let y = 0; y < dh; y++) {
    const y0 = Math.floor(y * sy);
    const y1 = Math.min(h, Math.max(y0 + 1, Math.floor((y + 1) * sy)));
    for (let x = 0; x < dw; x++) {
      const x0 = Math.floor(x * sx);
      const x1 = Math.min(w, Math.max(x0 + 1, Math.floor((x + 1) * sx)));
      let sum = 0, n = 0;
      for (let yy = y0; yy < y1; yy++) {
        const row = yy * w;
        for (let xx = x0; xx < x1; xx++) { sum += src[row + xx]; n++; }
      }
      out[y * dw + x] = sum / n;
    }
  }
  return out;
}

/** Bilinear upscale, sampling at pixel centres the way Pillow does. */
export function upscale(src, sw, sh, w, h) {
  const out = new Float32Array(w * h);
  const sx = sw / w, sy = sh / h;
  for (let y = 0; y < h; y++) {
    let fy = (y + 0.5) * sy - 0.5;
    if (fy < 0) fy = 0; else if (fy > sh - 1) fy = sh - 1;
    const y0 = Math.floor(fy), y1 = Math.min(y0 + 1, sh - 1), wy = fy - y0;
    for (let x = 0; x < w; x++) {
      let fx = (x + 0.5) * sx - 0.5;
      if (fx < 0) fx = 0; else if (fx > sw - 1) fx = sw - 1;
      const x0 = Math.floor(fx), x1 = Math.min(x0 + 1, sw - 1), wx = fx - x0;
      const a = src[y0 * sw + x0], b = src[y0 * sw + x1];
      const c = src[y1 * sw + x0], d = src[y1 * sw + x1];
      out[y * w + x] = (a + (b - a) * wx) * (1 - wy) + (c + (d - c) * wx) * wy;
    }
  }
  return out;
}

// --- blur -------------------------------------------------------------------

/**
 * Three box passes approximate a Gaussian to within a per cent or so, and cost the
 * same whatever the radius — which matters here, because the illumination estimate
 * needs a radius of tens of pixels and a true convolution at that size is slow
 * enough to be felt. Sizes from the standard box-blur approximation.
 */
function boxSizes(sigma, n) {
  const ideal = Math.sqrt((12 * sigma * sigma / n) + 1);
  let lower = Math.floor(ideal);
  if (lower % 2 === 0) lower--;
  if (lower < 1) lower = 1;
  const m = Math.round((12 * sigma * sigma - n * lower * lower - 4 * n * lower - 3 * n) /
                       (-4 * lower - 4));
  const sizes = [];
  for (let i = 0; i < n; i++) sizes.push(i < m ? lower : lower + 2);
  return sizes;
}

function boxH(src, dst, w, h, r) {
  if (r < 1) { dst.set(src); return; }
  const span = 2 * r + 1;
  for (let y = 0; y < h; y++) {
    const row = y * w;
    let sum = src[row] * (r + 1);
    for (let x = 1; x <= r; x++) sum += src[row + Math.min(x, w - 1)];
    for (let x = 0; x < w; x++) {
      dst[row + x] = sum / span;
      sum += src[row + Math.min(x + r + 1, w - 1)] - src[row + Math.max(x - r, 0)];
    }
  }
}

function boxV(src, dst, w, h, r) {
  if (r < 1) { dst.set(src); return; }
  const span = 2 * r + 1;
  for (let x = 0; x < w; x++) {
    let sum = src[x] * (r + 1);
    for (let y = 1; y <= r; y++) sum += src[Math.min(y, h - 1) * w + x];
    for (let y = 0; y < h; y++) {
      dst[y * w + x] = sum / span;
      sum += src[Math.min(y + r + 1, h - 1) * w + x] - src[Math.max(y - r, 0) * w + x];
    }
  }
}

export function gaussianBlur(src, w, h, sigma) {
  let a = Float32Array.from(src);
  if (sigma <= 0) return a;
  const b = new Float32Array(w * h);
  for (const size of boxSizes(sigma, 3)) {
    const r = (size - 1) >> 1;
    boxH(a, b, w, h, r);
    boxV(b, a, w, h, r);
  }
  return a;
}

// --- flat-field correction --------------------------------------------------

/**
 * Estimate the illumination by blurring every trace of content away.
 *
 * The radius has to be far larger than a letter, or the text blurs into the
 * estimate and gets divided out along with the shadow, and far smaller than the
 * sheet, or it stops following the gradient of the light. Four and a half per cent
 * of the width is the compromise clean_scan.py settled on for photographed A4.
 */
export function lightField(grey, w, h, radiusRel = 0.045) {
  const sw = Math.max(w >> 3, 1), sh = Math.max(h >> 3, 1);
  const small = downscale(grey, w, h, sw, sh);
  const blurred = gaussianBlur(small, sw, sh, Math.max(radiusRel * w / 8, 2));
  return upscale(blurred, sw, sh, w, h);
}

/** Divide the image by the illumination map. This is the whole trick. */
export function flatten(grey, light) {
  const out = new Float32Array(grey.length);
  for (let i = 0; i < grey.length; i++) {
    const v = grey[i] * (255 / Math.max(light[i], 1));
    out[i] = v > 255 ? 255 : v < 0 ? 0 : v;
  }
  return out;
}

/** Greyscale in, flat-fielded greyscale out. The basis for every measurement. */
export function flattened(grey, w, h) {
  return flatten(grey, lightField(grey, w, h));
}

// --- statistics -------------------------------------------------------------

/**
 * Percentile with linear interpolation, matching numpy's default.
 *
 * Above the sample limit it measures a regular subsample instead of sorting eight
 * million floats: the white point moves by hundredths of a grey level and the tool
 * answers in a second rather than four.
 */
export function percentile(values, p, sampleLimit = 2000000) {
  let sample;
  if (values.length <= sampleLimit) {
    sample = Float32Array.from(values);
  } else {
    const stride = Math.ceil(values.length / sampleLimit);
    sample = new Float32Array(Math.ceil(values.length / stride));
    for (let i = 0, j = 0; i < values.length; i += stride, j++) sample[j] = values[i];
  }
  sample.sort();
  const pos = (p / 100) * (sample.length - 1);
  const lo = Math.floor(pos), hi = Math.min(lo + 1, sample.length - 1);
  return sample[lo] + (sample[hi] - sample[lo]) * (pos - lo);
}

/** Stretch so that `black` maps to 0 and `white` to 255. */
export function levels(src, black, white) {
  const scale = 255 / Math.max(white - black, 1);
  const out = new Float32Array(src.length);
  for (let i = 0; i < src.length; i++) {
    const v = (src[i] - black) * scale;
    out[i] = v > 255 ? 255 : v < 0 ? 0 : v;
  }
  return out;
}

/**
 * Pillow's ImageOps.autocontrast with a (low, high) cutoff, as a lookup table.
 *
 * Ported operation by operation rather than reinvented, because photo_to_pdf.py
 * ships this exact call and the two have to agree on the same photograph.
 */
export function autocontrastLut(grey, lowCut, highCut) {
  const hist = new Int32Array(256);
  for (let i = 0; i < grey.length; i++) {
    let v = Math.round(grey[i]);
    if (v < 0) v = 0; else if (v > 255) v = 255;
    hist[v]++;
  }
  const n = grey.length;

  let cut = Math.floor(n * lowCut / 100);
  for (let lo = 0; lo < 256 && cut > 0; lo++) {
    if (cut > hist[lo]) { cut -= hist[lo]; hist[lo] = 0; }
    else { hist[lo] -= cut; cut = 0; }
  }
  cut = Math.floor(n * highCut / 100);
  for (let hi = 255; hi >= 0 && cut > 0; hi--) {
    if (cut > hist[hi]) { cut -= hist[hi]; hist[hi] = 0; }
    else { hist[hi] -= cut; cut = 0; }
  }

  let lo = 0, hi = 255;
  while (lo < 256 && !hist[lo]) lo++;
  while (hi >= 0 && !hist[hi]) hi--;

  const lut = new Uint8ClampedArray(256);
  if (hi <= lo) {
    for (let i = 0; i < 256; i++) lut[i] = i;
  } else {
    const scale = 255 / (hi - lo);
    // Truncation, not rounding: Pillow builds its table with int(), and a tool that
    // says it matches the CLI has to match it here too.
    for (let i = 0; i < 256; i++) lut[i] = Math.trunc((i - lo) * scale);
  }
  return lut;
}

// --- sharpening -------------------------------------------------------------

/** Pillow's UnsharpMask: add back what the blur removed, above a threshold. */
export function unsharpMask(src, w, h, radius = 1.2, percent = 55, threshold = 3) {
  const blur = gaussianBlur(src, w, h, radius);
  const out = new Float32Array(src.length);
  const k = percent / 100;
  for (let i = 0; i < src.length; i++) {
    const diff = src[i] - blur[i];
    const v = Math.abs(diff) >= threshold ? src[i] + diff * k : src[i];
    out[i] = v > 255 ? 255 : v < 0 ? 0 : v;
  }
  return out;
}

// --- finding the ink --------------------------------------------------------

/**
 * Bounding box of the dark pixels, ignoring rows and columns with only a speck in
 * them. A single dust mote in a corner would otherwise decide the whole layout.
 */
export function inkBox(grey, w, h, dark = 170, minCount = 2) {
  const rows = new Int32Array(h), cols = new Int32Array(w);
  for (let y = 0; y < h; y++) {
    const off = y * w;
    for (let x = 0; x < w; x++) if (grey[off + x] < dark) { rows[y]++; cols[x]++; }
  }
  let y0 = -1, y1 = -1, x0 = -1, x1 = -1;
  for (let y = 0; y < h; y++) if (rows[y] > minCount) { if (y0 < 0) y0 = y; y1 = y; }
  for (let x = 0; x < w; x++) if (cols[x] > minCount) { if (x0 < 0) x0 = x; x1 = x; }
  if (y0 < 0 || x0 < 0) return null;
  return { x0, y0, x1, y1, rows: y1 - y0 + 1, cols: x1 - x0 + 1 };
}

/** Trim a signature to its strokes, with a little padding so it does not look cut. */
export function alphaBBox(alpha, w, h, threshold = 30, pad = 6) {
  let x0 = w, y0 = h, x1 = -1, y1 = -1;
  for (let y = 0; y < h; y++) {
    const off = y * w;
    for (let x = 0; x < w; x++) {
      if (alpha[off + x] > threshold) {
        if (x < x0) x0 = x;
        if (x > x1) x1 = x;
        if (y < y0) y0 = y;
        if (y > y1) y1 = y;
      }
    }
  }
  if (x1 < 0) return null;
  return {
    x0: Math.max(x0 - pad, 0), y0: Math.max(y0 - pad, 0),
    x1: Math.min(x1 + 1 + pad, w), y1: Math.min(y1 + 1 + pad, h),
  };
}

// --- the signature ----------------------------------------------------------

/**
 * Build the alpha channel from how dark each pixel is: a ramp, not a step.
 *
 * Above `light` it is paper and goes fully transparent, below `dark` it is solid
 * ink, and in between it fades. A hard threshold gives a signature with staircase
 * edges that reads as pasted on at a glance.
 */
export function signatureAlpha(flat, light = 205, dark = 95) {
  const span = Math.max(light - dark, 1);
  const out = new Float32Array(flat.length);
  for (let i = 0; i < flat.length; i++) {
    const v = (light - flat[i]) / span * 255;
    out[i] = v > 255 ? 255 : v < 0 ? 0 : v;
  }
  return out;
}

/**
 * Crop, flat-field, and cut the signature out as RGBA with a real alpha channel.
 * `keepColour` keeps the pen's own colour instead of forcing black.
 */
export function extractSignature(rgba, w, h, opts = {}) {
  const { light = 205, dark = 95, keepColour = false, pad = 6 } = opts;
  const grey = toGrey(rgba, w, h);
  const illumination = lightField(grey, w, h);
  const flat = flatten(grey, illumination);
  const alpha = signatureAlpha(flat, light, dark);

  const out = new Uint8ClampedArray(w * h * 4);
  for (let i = 0, p = 0; i < alpha.length; i++, p += 4) {
    if (keepColour) {
      const gain = 255 / Math.max(illumination[i], 1) * 0.75;
      out[p] = rgba[p] * gain;
      out[p + 1] = rgba[p + 1] * gain;
      out[p + 2] = rgba[p + 2] * gain;
    }
    out[p + 3] = alpha[i];
  }

  const box = alphaBBox(alpha, w, h, 30, pad);
  let covered = 0;
  for (let i = 0; i < alpha.length; i++) if (alpha[i] > 30) covered++;
  return { rgba: out, width: w, height: h, box, coverage: covered / alpha.length * 100 };
}

// --- geometry ---------------------------------------------------------------

/** Rotate anticlockwise about the centre, bilinear, filling outside with `fill`. */
export function rotate(src, w, h, degrees, fill = 255) {
  const out = new Float32Array(w * h);
  const a = degrees * Math.PI / 180;
  const cos = Math.cos(a), sin = Math.sin(a);
  const cx = (w - 1) / 2, cy = (h - 1) / 2;
  for (let y = 0; y < h; y++) {
    const dy = y - cy;
    for (let x = 0; x < w; x++) {
      const dx = x - cx;
      const sx = cos * dx + sin * dy + cx;
      const sy = -sin * dx + cos * dy + cy;
      if (sx < 0 || sy < 0 || sx > w - 1 || sy > h - 1) { out[y * w + x] = fill; continue; }
      const x0 = Math.floor(sx), y0 = Math.floor(sy);
      const x1 = Math.min(x0 + 1, w - 1), y1 = Math.min(y0 + 1, h - 1);
      const fx = sx - x0, fy = sy - y0;
      const p = src[y0 * w + x0], q = src[y0 * w + x1];
      const r = src[y1 * w + x0], s = src[y1 * w + x1];
      out[y * w + x] = (p + (q - p) * fx) * (1 - fy) + (r + (s - r) * fx) * fy;
    }
  }
  return out;
}

/**
 * Slant of the text lines, by the projection-profile method.
 *
 * Rotate the page through a range of angles and, for each one, sum the dark pixels
 * row by row. With the lines horizontal that sum is spiky — full rows alternating
 * with empty leading. With them slanted the text smears across rows and the profile
 * flattens. Maximising the change between neighbouring rows finds the angle without
 * recognising a single letter.
 *
 * Coarse half-degree pass first, then a twentieth of a degree around the winner:
 * searching fine across the whole range costs twenty times as much for the same
 * answer.
 */
export function textLineAngle(grey, w, h, limit = 6) {
  const tw = 700, th = Math.max(Math.round(700 * h / w), 40);
  const small = w === tw ? grey : downscale(grey, w, h, tw, th);

  // Nothing to measure means no answer. A band of blank paper produces a profile
  // whose only variation comes from the white corners the rotation fills in, and the
  // winner of that is noise: on a short letter with white space below the text, it
  // came back as six degrees and warped a perfectly straight page. Check there is ink
  // in the band before believing anything measured in it.
  let ink = 0;
  for (let i = 0; i < small.length; i++) if (small[i] < 170) ink++;
  if (ink / small.length < 0.002) return 0;

  const score = (angle) => {
    const r = rotate(small, tw, th, angle, 255);
    let previous = 0, total = 0;
    for (let y = 0; y < th; y++) {
      let sum = 0;
      const off = y * tw;
      for (let x = 0; x < tw; x++) sum += 255 - r[off + x];
      if (y) { const d = sum - previous; total += d * d; }
      previous = sum;
    }
    return total;
  };

  // Stepping by index rather than by accumulating 0.05 at a time: the accumulated
  // error is enough to miss the last angle of the range, which is exactly where the
  // answer sits when the page is tilted by a round number of degrees. `>=` keeps the
  // larger of two equal scores, the way numpy's max over (score, angle) pairs does.
  let best = -Infinity, bestAngle = 0;
  const coarse = Math.round(2 * limit / 0.5);
  for (let i = 0; i <= coarse; i++) {
    const a = -limit + i * 0.5;
    const s = score(a);
    if (s >= best) { best = s; bestAngle = a; }
  }
  let fine = best, fineAngle = bestAngle;
  for (let i = 0; i <= 24; i++) {
    const a = bestAngle - 0.6 + i * 0.05;
    const s = score(a);
    if (s >= fine) { fine = s; fineAngle = a; }
  }
  return fineAngle;
}

/**
 * Coefficients of the projective map, in the target-to-source direction the
 * resampler wants: for each output pixel it says where to read the input.
 * Four point pairs determine it exactly, so this is one 8x8 solve.
 */
export function perspectiveCoeffs(target, source) {
  const A = [], B = [];
  for (let i = 0; i < 4; i++) {
    const [xd, yd] = target[i], [xs, ys] = source[i];
    A.push([xd, yd, 1, 0, 0, 0, -xs * xd, -xs * yd]);
    A.push([0, 0, 0, xd, yd, 1, -ys * xd, -ys * yd]);
    B.push(xs, ys);
  }
  return solve(A, B);
}

/** Gaussian elimination with partial pivoting. Eight unknowns; nothing exotic. */
export function solve(A, b) {
  const n = b.length;
  const m = A.map((row, i) => row.concat([b[i]]));
  for (let col = 0; col < n; col++) {
    let pivot = col;
    for (let r = col + 1; r < n; r++) {
      if (Math.abs(m[r][col]) > Math.abs(m[pivot][col])) pivot = r;
    }
    if (Math.abs(m[pivot][col]) < 1e-12) throw new Error("singular matrix");
    [m[col], m[pivot]] = [m[pivot], m[col]];
    for (let r = 0; r < n; r++) {
      if (r === col) continue;
      const f = m[r][col] / m[col][col];
      if (!f) continue;
      for (let c = col; c <= n; c++) m[r][c] -= f * m[col][c];
    }
  }
  return m.map((row, i) => row[n] / m[i][i]);
}

/** Resample RGBA through a projective map. Bilinear, edges filled with `fill`. */
export function warp(rgba, w, h, outW, outH, c, fill = 255) {
  const out = new Uint8ClampedArray(outW * outH * 4);
  for (let y = 0; y < outH; y++) {
    for (let x = 0; x < outW; x++) {
      const d = c[6] * x + c[7] * y + 1;
      const sx = (c[0] * x + c[1] * y + c[2]) / d;
      const sy = (c[3] * x + c[4] * y + c[5]) / d;
      const p = (y * outW + x) * 4;
      out[p + 3] = 255;
      if (sx < 0 || sy < 0 || sx > w - 1 || sy > h - 1) {
        out[p] = out[p + 1] = out[p + 2] = fill;
        continue;
      }
      const x0 = Math.floor(sx), y0 = Math.floor(sy);
      const x1 = Math.min(x0 + 1, w - 1), y1 = Math.min(y0 + 1, h - 1);
      const fx = sx - x0, fy = sy - y0;
      for (let ch = 0; ch < 3; ch++) {
        const a = rgba[(y0 * w + x0) * 4 + ch], b = rgba[(y0 * w + x1) * 4 + ch];
        const cc = rgba[(y1 * w + x0) * 4 + ch], dd = rgba[(y1 * w + x1) * 4 + ch];
        out[p + ch] = (a + (b - a) * fx) * (1 - fy) + (cc + (dd - cc) * fx) * fy;
      }
    }
  }
  return out;
}

/**
 * One pass of perspective straightening, derived from the text and not from the
 * edge of the sheet — which is often not in the frame, or sits against a background
 * brighter than the paper.
 *
 * A sheet photographed at an angle is a trapezoid, not a rotated rectangle: on the
 * case clean_scan.py was written for, the slant of the lines ran from 0.00 degrees
 * at the top to 1.00 at the bottom, and no single rotation fixes that. Two measured
 * angles plus the bounding box of the text reconstruct the trapezoid; the projective
 * transform redistributes the intermediate slant by itself.
 */
export function straightenPass(rgba, w, h) {
  const flat = flattened(toGrey(rgba, w, h), w, h);
  const box = inkBox(flat, w, h, 170, 3);
  if (!box || box.rows < 20 || box.cols < 20) return { rgba, width: w, height: h, fan: 0 };

  // The bands are cut out of the block of TEXT, not out of the frame. Taking them at
  // fixed fractions of the photograph works only when the document fills it; on a
  // short letter with white space below, the lower band lands on blank paper and the
  // angle measured there is noise.
  const band = (from, to) => {
    const bh = to - from;
    if (bh < 12) return 0;
    const strip = new Float32Array(w * bh);
    for (let y = 0; y < bh; y++) strip.set(flat.subarray((from + y) * w, (from + y) * w + w), y * w);
    return textLineAngle(strip, w, bh);
  };
  const { x0, y0, x1, y1 } = box;
  const textHeight = y1 - y0;
  const top = band(y0, y0 + Math.floor(textHeight * 0.4)) * Math.PI / 180;
  const bottom = band(y0 + Math.ceil(textHeight * 0.6), y1) * Math.PI / 180;

  const width = x1 - x0, height = textHeight;
  const source = [[x0, y0], [x1, y0 + width * Math.tan(top)],
                  [x1, y1 + width * Math.tan(bottom)], [x0, y1]];
  const target = [[0, 0], [width, 0], [width, height], [0, height]];
  const coeffs = perspectiveCoeffs(target, source);

  return {
    rgba: warp(rgba, w, h, width, height, coeffs, 255),
    width, height,
    fan: Math.abs((bottom - top) * 180 / Math.PI),
  };
}

/**
 * Where the text sits on a rebuilt A4 sheet.
 *
 * A phone photo has a ratio near 0.81 and A4 has 0.707, so laid on the page it
 * leaves white bands top and bottom and the document looks like it is floating.
 * Cropping to even the ratio out would need more width than the margins hold and
 * would cut into the text, so paper gets added instead — seven per cent at the
 * sides and three and a half at the top, the margins of an ordinary document, with
 * the remainder falling to the bottom. That is not an imbalance: a one-page CV that
 * ends two thirds down has a lot of white below it, and centring it would make the
 * page read as a letter.
 */
export function a4Canvas(textW, textH, side = 0.07, top = 0.035) {
  let canvasW = Math.round(textW / (1 - 2 * side));
  let canvasH = Math.round(canvasW / 0.70711);
  const minimum = Math.round(textH / (1 - top - 0.04));
  if (canvasH < minimum) {
    canvasH = minimum;
    canvasW = Math.round(minimum * 0.70711);
  }
  return {
    canvasW, canvasH,
    marginX: Math.round(canvasW * side),
    marginY: Math.round(canvasH * top),
  };
}

// --- the whole cleanup ------------------------------------------------------

/**
 * Flat-field, set a white and a black point, sharpen a little.
 *
 * The white point is a high percentile of the corrected image, which is the paper;
 * the black point sits just above zero so the thin strokes of a signature are not
 * crushed into a blob. `strength` pulls the white point down — higher means whiter
 * paper, and above about 1.15 it starts eating light ink.
 */
export function cleanScan(rgba, w, h, opts = {}) {
  const { colour = false, strength = 1.06 } = opts;
  const grey = toGrey(rgba, w, h);
  const light = lightField(grey, w, h);

  const channels = colour ? 3 : 1;
  const corrected = [];
  for (let ch = 0; ch < channels; ch++) {
    const out = new Float32Array(w * h);
    for (let i = 0, p = ch; i < out.length; i++, p += 4) {
      const gain = 255 / Math.max(light[i], 1);
      const v = (colour ? rgba[p] : grey[i]) * gain;
      out[i] = v > 255 ? 255 : v < 0 ? 0 : v;
    }
    corrected.push(out);
  }

  let reference = corrected[0];
  if (colour) {
    reference = new Float32Array(w * h);
    for (let i = 0; i < reference.length; i++) {
      reference[i] = (corrected[0][i] + corrected[1][i] + corrected[2][i]) / 3;
    }
  }
  const black = percentile(reference, 2);
  let white = Math.max(percentile(reference, 92), black + 20);
  white = black + (white - black) / strength;

  const out = new Uint8ClampedArray(w * h * 4);
  for (let ch = 0; ch < channels; ch++) {
    const stretched = unsharpMask(levels(corrected[ch], black, white), w, h);
    for (let i = 0, p = ch; i < stretched.length; i++, p += 4) {
      if (colour) out[p] = stretched[i];
      else { const v = stretched[i]; out[i * 4] = out[i * 4 + 1] = out[i * 4 + 2] = v; }
    }
  }
  for (let p = 3; p < out.length; p += 4) out[p] = 255;
  return { rgba: out, width: w, height: h, black, white };
}
