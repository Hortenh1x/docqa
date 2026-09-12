import { createHash } from "node:crypto";
import { lstatSync, readFileSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
const sha256 = bytes => createHash("sha256").update(bytes).digest("hex");

function readRegular(name) {
  if (path.isAbsolute(name) || name.split("/").includes("..") || name.includes("\\")) {
    throw new Error("Invalid source manifest path");
  }
  let filename = root;
  for (const part of name.split("/")) {
    filename = path.join(filename, part);
    if (lstatSync(filename).isSymbolicLink()) throw new Error(`Refusing source symlink: ${name}`);
  }
  if (!lstatSync(filename).isFile()) throw new Error(`Not a regular source file: ${name}`);
  return readFileSync(filename);
}

try {
  let bytes;
  try { bytes = readRegular("public/source/manifest.json"); }
  catch (error) {
    if (error.code === "ENOENT" && process.argv.includes("--optional")) {
      console.log("Local build: no corresponding-source download packaged.");
      process.exit(0);
    }
    throw error;
  }
  const offer = JSON.parse(bytes);
  if (offer.format !== 1 || !/^docqa-source-[a-f0-9]{64}\.tar\.gz$/.test(offer.archive) ||
      !/^[a-f0-9]{64}$/.test(offer.sha256) || !offer.files) {
    throw new Error("Invalid source release manifest");
  }
  if (sha256(readRegular(`public/source/${offer.archive}`)) !== offer.sha256) {
    throw new Error("Archive checksum does not match the source release");
  }
  if (sha256(readRegular("public/source/LICENSE.txt")) !== offer.files.LICENSE?.sha256) {
    throw new Error("Source license checksum does not match");
  }
  for (const [name, file] of Object.entries(offer.files)) {
    if (!name.startsWith("ui/") || name.startsWith("ui/tests/") || name === "ui/.env.example") continue;
    if (sha256(readRegular(name.slice(3))) !== file.sha256) {
      throw new Error(`Source changed after packaging: ${name}`);
    }
  }
  console.log(`Verified corresponding source: ${offer.archive}`);
} catch (error) {
  console.error(`Source verification failed: ${error.message}. Prepare a new release with scripts/build_source.py.`);
  process.exit(1);
}
