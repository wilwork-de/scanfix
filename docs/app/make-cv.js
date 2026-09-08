/**
 * The CV page: fill the form in, get a one-page PDF.
 *
 * The layout lives in ../cv-core.js, a port of tools/make_cv.py. Nothing typed here
 * is stored or sent: the fields exist only in this tab, and closing it loses them.
 */

import * as PDFLib from "../vendor/pdf-lib.esm.min.js";
import { buildCv, parseEntries, parsePairs, parseLines } from "../cv-core.js";
import { parseDate } from "../sign-core.js";
import {
  $, status, yieldToPaint, bytesOf, offerDownload, humanSize, isoToday, escapeHtml,
} from "./ui.js";

const state = $("state");
const save = $("save");
const notes = $("notes");

$("date").value = isoToday();
$("build").addEventListener("click", build);

const value = id => $(id).value.trim();

async function build() {
  save.hidden = true;
  notes.innerHTML = "";

  if (!value("first_name") && !value("last_name")) {
    status(state, "A CV needs a name at the top. Fill in the first two fields.", "bad");
    return;
  }

  try {
    status(state, "Laying out the page…");
    await yieldToPaint();

    const data = {
      first_name: value("first_name"), last_name: value("last_name"),
      headline: value("headline"), born_on: value("born_on"), born_in: value("born_in"),
      address: value("address"), phone: value("phone"), email: value("email"),
      linkedin: value("linkedin"), licence: value("licence"), citizenship: value("citizenship"),
      education: parseEntries(value("education")),
      experience: parseEntries(value("experience")),
      skills: parsePairs(value("skills")),
      languages: parsePairs(value("languages")),
      other: parseLines(value("other")),
    };

    const options = {
      locale: $("locale").value,
      place: value("place"),
      date: parseDate($("date").value || isoToday()),
      signature: null,
    };
    const picked = $("signature").files[0];
    if (picked) {
      options.signature = {
        bytes: await bytesOf(picked),
        type: /\.png$/i.test(picked.name) || picked.type === "image/png" ? "png" : "jpg",
      };
    }

    const cv = await buildCv(data, options, PDFLib);
    const blob = new Blob([cv.bytes], { type: "application/pdf" });
    const name = `CV_${data.first_name}_${data.last_name}`.replace(/[^A-Za-z0-9_-]+/g, "_");
    offerDownload(save, blob, `${name}.pdf`);
    save.textContent = `Save the CV (${humanSize(blob.size)})`;

    const remarks = [];
    if (cv.pages > 1) {
      remarks.push(`It came to ${cv.pages} pages. A CV at this level reads better on one: ` +
                   `cut the oldest entry, or a bullet from each job.`);
    }
    if (cv.dropped.length) {
      // The core PDF fonts cover Western European text and nothing else. Saying which
      // characters went missing beats a CV that quietly loses a name.
      remarks.push(`These characters are outside what the built-in PDF fonts can encode ` +
                   `and were left out: ${cv.dropped.join(" ")}. Write those words in the ` +
                   `Latin alphabet, or use the command-line version with a font of your own.`);
    }
    if (!picked) {
      remarks.push(`The signature rule is empty. Institutional portals want a handwritten ` +
                   `signature: sign a blank sheet, cut it out with ` +
                   `<a href="../extract-signature/">the signature extractor</a>, and add it above.`);
    }
    if ($("locale").value === "it") {
      remarks.push(`The Italian version carries the GDPR authorisation line, which Italian ` +
                   `employers and public bodies expect to see.`);
    }
    notes.innerHTML = remarks.length ? "<ul>" + remarks.map(r => `<li>${r}</li>`).join("") + "</ul>" : "";
    status(state, `One-page CV, ${cv.pages === 1 ? "one page" : cv.pages + " pages"}, ` +
                  `dated ${escapeHtml(cv.date)}.`, "good");
  } catch (err) {
    status(state, `Could not build it: ${err && err.message || err}`, "bad");
  }
}
