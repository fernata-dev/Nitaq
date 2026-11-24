// Runs the checks off the main thread so the page stays smooth on phones.
import {checkFile, checkText} from "./check.js";

self.onmessage = async (e) => {
  const {id, name, bytes, text} = e.data || {};
  try {
    const rep = bytes ? await checkFile(name, new Uint8Array(bytes)) : await checkText(text, name);
    self.postMessage({id, rep});
  } catch (err) {
    self.postMessage({id, error: String((err && err.message) || err)});
  }
};
